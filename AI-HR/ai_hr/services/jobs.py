"""Job service orchestrates job-related use cases."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ..connectors.base import ConnectorCredentials
from ..connectors.registry import registry
from ..core.config import get_settings
from ..core.exceptions import ConnectorOperationError
from ..repositories.candidates import CandidateRepository
from ..repositories.job_candidates import JobCandidateRepository
from ..repositories.jobs import JobRepository
from ..schemas.candidates import CandidateImportItem
from ..schemas.jobs import (
    JobCandidateSyncRequest,
    JobCandidateSyncResult,
    JobCreateRequest,
    JobPublishRequest,
    JobResumeReadySyncRequest,
    JobResumeReadySyncResult,
    JobUpdateSettingsRequest,
    RemoteJobSyncItem,
)
from .credentials import get_credential_service, CredentialService

logger = logging.getLogger(__name__)


class JobService:
    def __init__(
        self,
        repository: JobRepository,
        candidate_repository: CandidateRepository,
        job_candidate_repository: JobCandidateRepository,
        credential_service: CredentialService,
    ):
        self._repository = repository
        self._candidate_repository = candidate_repository
        self._job_candidate_repository = job_candidate_repository
        self._credential_service = credential_service
        self._settings = get_settings()

    def create_job(self, payload: JobCreateRequest):
        return self._repository.create(payload)

    def get_job(self, job_id: str):
        return self._repository.get(job_id)

    def list_jobs(
        self,
        limit: int = 100,
        offset: int = 0,
        *,
        platform: str | None = None,
        name: str | None = None,
        job_type: str | None = None,
        salary: str | None = None,
    ):
        return self._repository.list_all(
            limit=limit,
            offset=offset,
            platform=platform,
            name=name,
            job_type=job_type,
            salary=salary,
        )

    def delete_job(self, job_id: str) -> None:
        self._repository.delete(job_id)

    def batch_delete_jobs(self, job_ids: list[str]) -> int:
        return self._repository.delete_many(job_ids)

    def update_job_settings(self, job_id: str, payload: JobUpdateSettingsRequest):
        """更新岗位自动化配置。"""
        return self._repository.update_settings(
            job_id,
            auto_request_resume=payload.auto_request_resume,
            min_degree=payload.min_degree,
            min_experience_years=payload.min_experience_years,
            max_daily_resume_requests=payload.max_daily_resume_requests,
        )

    def publish_job(self, job_id: str, payload: JobPublishRequest):
        job = self._repository.get(job_id)
        for channel in payload.channels:
            publication_request = {
                "title": job.title,
                "department": job.department,
                "city": job.city,
                "salary_range": job.salary_range,
                "requirements": job.requirements,
            }
            try:
                connector = self._build_connector(channel)
                result = connector.publish_job(publication_request)
                self._repository.add_publication(
                    job,
                    channel=channel,
                    status=result.status,
                    request_payload=publication_request,
                    response_payload=result.raw_payload,
                    external_job_id=result.external_job_id,
                )
            except ConnectorOperationError as exc:
                self._repository.add_publication(
                    job,
                    channel=channel,
                    status="failed",
                    request_payload=publication_request,
                    response_payload={},
                    error_message=str(exc),
                )
        return self._repository.get(job_id)

    def get_publish_status(self, job_id: str):
        job = self._repository.get(job_id)
        for publication in list(job.publications):
            if not publication.external_job_id:
                continue
            try:
                connector = self._build_connector(publication.channel)
                sync_result = connector.sync_job_status(publication.external_job_id)
                self._repository.update_publication_sync_result(
                    publication.id,
                    status=sync_result.status,
                    response_payload=sync_result.raw_payload,
                )
            except ConnectorOperationError as exc:
                self._repository.update_publication_sync_result(
                    publication.id,
                    status="failed",
                    response_payload={},
                    error_message=str(exc),
                )

        job = self._repository.get(job_id)
        return {
            "job_id": job.id,
            "publications": list(job.publications),
        }

    def list_remote_jobs(self, channel: str, page: int = 1, page_size: int = 20):
        connector = self._build_connector(channel)
        result = connector.list_jobs(page=page, page_size=page_size)
        return {
            "channel": channel,
            "page": page,
            "page_size": page_size,
            "jobs": [
                {
                    "external_job_id": item.get("external_job_id"),
                    "title": item.get("title") or "Untitled Job",
                    "status": item.get("status"),
                    "city": item.get("city"),
                    "salary": item.get("salary"),
                    "raw_payload": item,
                }
                for item in result.get("items", [])
                if item.get("external_job_id")
            ],
        }

    def import_remote_jobs(self, channel: str, page: int = 1, page_size: int = 20):
        remote_jobs = self.list_remote_jobs(channel, page=page, page_size=page_size)["jobs"]
        synced_jobs = []
        created_count = 0
        updated_count = 0
        for item in remote_jobs:
            normalized = RemoteJobSyncItem(
                external_job_id=item["external_job_id"],
                title=item["title"],
                status=item.get("status") or "published",
                city=item.get("city") or "Unknown",
                salary=item.get("salary"),
                raw_payload=item.get("raw_payload", {}),
            )
            job, _, created = self._repository.sync_remote_job(channel, normalized)
            synced_jobs.append(job)
            if created:
                created_count += 1
            else:
                updated_count += 1
        return {
            "channel": channel,
            "created_count": created_count,
            "updated_count": updated_count,
            "jobs": synced_jobs,
        }

    def sync_candidates(self, job_id: str, payload: JobCandidateSyncRequest):
        job = self._repository.get(job_id)
        allowed_channels = set(payload.channels or [])
        sync_targets = []
        for publication in list(job.publications):
            if not publication.external_job_id:
                continue
            if allowed_channels and publication.channel not in allowed_channels:
                continue
            sync_targets.append(publication)

        channel_results: list[dict] = []
        total_pulled = 0
        total_created = 0
        total_updated = 0
        synced_candidate_ids: list[str] = []

        for publication in sync_targets:
            connector = self._build_connector(publication.channel)
            cursor = None if payload.reset_cursor else publication.applicant_sync_cursor
            pulled_count = 0
            created_count = 0
            updated_count = 0
            has_more = False

            for _ in range(payload.max_pages):
                result = connector.list_applicants(publication.external_job_id, cursor=cursor)
                items = result.get("items", [])
                candidate_items = [
                    CandidateImportItem(
                        name=item.get("name", "Unknown"),
                        source_channel=publication.channel,
                        external_candidate_id=item["external_candidate_id"],
                        phone_hash=item.get("phone_hash"),
                        email_hash=item.get("email_hash"),
                        resume_url=item.get("resume_url"),
                        resume_text=item.get("resume_text"),
                        school=item.get("school"),
                        degree=item.get("degree"),
                        work_experience=item.get("work_experience"),
                        expected_salary=item.get("expected_salary"),
                        latest_company=item.get("latest_company"),
                        applied_at=item.get("applied_at"),
                        raw_profile=item.get("raw_profile", {}),
                    )
                    for item in items
                    if item.get("external_candidate_id")
                ]

                if candidate_items:
                    candidates, page_created, page_updated = self._candidate_repository.upsert_many(candidate_items)
                    for candidate, source_item in zip(candidates, candidate_items, strict=False):
                        synced_candidate_ids.append(candidate.id)
                        self._job_candidate_repository.upsert_link(
                            job_id=job.id,
                            publication_id=publication.id,
                            candidate_id=candidate.id,
                            channel=publication.channel,
                            external_job_id=publication.external_job_id,
                            external_candidate_id=source_item.external_candidate_id,
                            stage=candidate.current_stage,
                            source_status=source_item.raw_profile.get("status"),
                            applied_at=source_item.applied_at,
                            source_payload=source_item.raw_profile,
                        )
                    created_count += page_created
                    updated_count += page_updated
                    
                    # 增量优化：如果当前页没有抓取到任何新数据或更新数据，且不是重置游标模式，
                    # 则说明我们已经同步到了历史交界处，可以提前停止以提升性能。
                    if not payload.reset_cursor and page_created == 0 and page_updated == 0:
                        break
                pulled_count += len(candidate_items)

                cursor = result.get("next_cursor")
                has_more = bool(result.get("has_more", False))
                if not has_more or cursor is None:
                    break

            self._repository.update_publication_cursor(publication.id, cursor)
            channel_results.append(
                {
                    "channel": publication.channel,
                    "external_job_id": publication.external_job_id,
                    "pulled_count": pulled_count,
                    "created_count": created_count,
                    "updated_count": updated_count,
                    "next_cursor": cursor,
                    "has_more": has_more,
                }
            )
            total_pulled += pulled_count
            total_created += created_count
            total_updated += updated_count

        return {
            "job_id": job.id,
            "total_pulled": total_pulled,
            "total_created": total_created,
            "total_updated": total_updated,
            "channels": channel_results,
            "synced_candidate_ids": synced_candidate_ids,
        }

    def list_job_candidates(
        self,
        job_id: str,
        *,
        limit: int = 30,
        cursor: str | None = None,
        keyword: str | None = None,
        resume_status: str | None = None,
        segment: str | None = None,
    ):
        self._repository.get(job_id)
        stats = self._job_candidate_repository.get_job_stats(job_id)
        items, next_cursor, has_more = self._job_candidate_repository.list_by_job(
            job_id,
            limit=limit,
            cursor=cursor,
            keyword=keyword,
            resume_status=resume_status,
            candidate_segment=segment,
        )
        return {
            "job_id": job_id,
            "total": stats["total"],
            "evaluated_count": stats["evaluated"],
            "sent_count": stats["sent"],
            "limit": limit,
            "next_cursor": next_cursor,
            "has_more": has_more,
            "candidates": [
                {
                    "candidate": item.candidate,
                    "channel": item.channel,
                    "external_candidate_id": item.external_candidate_id,
                    "external_job_id": item.external_job_id,
                    "stage": item.stage,
                    "source_status": item.source_status,
                    "applied_at": item.applied_at,
                    "first_synced_at": item.first_synced_at,
                    "last_synced_at": item.last_synced_at,
                    # Keep list response lightweight for table rendering.
                    "source_payload": {},
                    # Pipeline status mapping
                    "resume_request_status": item.pipeline.resume_request_status if item.pipeline else None,
                    "resume_download_status": item.pipeline.resume_download_status if item.pipeline else None,
                    "last_resume_requested_at": item.pipeline.last_resume_requested_at if item.pipeline else None,
                    # 性能优化：内嵌查询到的评估和投递数据
                    "evaluation": item.evaluation,
                    "latest_delivery": item.latest_delivery,
                }
                for item in items
            ],
        }

    def get_job_candidate(self, job_id: str, candidate_id: str):
        from ..core.exceptions import ResourceNotFoundError

        self._repository.get(job_id)
        item = self._job_candidate_repository.get_link_detail(job_id, candidate_id)
        if item is None:
            raise ResourceNotFoundError(f"Link between job {job_id} and candidate {candidate_id} not found")
        return item

    def update_candidate_stage(self, job_id: str, candidate_id: str, stage: str):
        from ..core.exceptions import ResourceNotFoundError
        link = self._job_candidate_repository.get_link(job_id, candidate_id)
        if link is None:
            raise ResourceNotFoundError(f"Link between job {job_id} and candidate {candidate_id} not found")
        return self._job_candidate_repository.update_stage(link, stage)

    def link_candidate(self, job_id: str, candidate_id: str):
        """Create or refresh a local job-candidate link for imported candidates."""
        self._repository.get(job_id)
        candidate = self._candidate_repository.get(candidate_id)
        external_candidate_id = (candidate.external_candidate_id or candidate.id).strip()
        self._job_candidate_repository.upsert_link(
            job_id=job_id,
            publication_id=None,
            candidate_id=candidate.id,
            channel="local_script",
            external_job_id=None,
            external_candidate_id=external_candidate_id,
            stage=candidate.current_stage,
            source_status="imported",
            applied_at=None,
            source_payload={"source": "generate_interview_invite"},
        )
        # Reuse existing repository commit path to persist the link in current transaction scope.
        self._candidate_repository.update_stage(candidate.id, candidate.current_stage)
        item = self._job_candidate_repository.get_link_detail(job_id, candidate_id)
        return item

    def sync_resume_ready_candidates(self, job_id: str, payload: JobResumeReadySyncRequest) -> JobResumeReadySyncResult:
        job = self._repository.get(job_id)
        publication = next(
            (
                item
                for item in job.publications
                if item.channel == payload.channel and item.external_job_id
            ),
            None,
        )
        if publication is None:
            raise ConnectorOperationError(f"No published external job found for channel '{payload.channel}'")

        connector = self._build_connector(payload.channel)
        result = connector.list_resume_ready_candidates(
            publication.external_job_id,
            label_id=payload.label_id,
            sort=payload.sort,
        )
        items = result.get("items", [])
        candidate_items = [
            CandidateImportItem(
                name=item.get("name", "Unknown"),
                source_channel=payload.channel,
                external_candidate_id=item["external_candidate_id"],
                phone_hash=item.get("phone_hash"),
                email_hash=item.get("email_hash"),
                resume_url=item.get("resume_url"),
                resume_text=item.get("resume_text"),
                raw_profile=item.get("raw_profile", {}),
            )
            for item in items
            if item.get("external_candidate_id")
        ]

        created_count = 0
        updated_count = 0
        if candidate_items:
            candidates, created_count, updated_count = self._candidate_repository.upsert_many(candidate_items)
            for candidate, source_item in zip(candidates, candidate_items, strict=False):
                self._job_candidate_repository.upsert_link(
                    job_id=job.id,
                    publication_id=publication.id,
                    candidate_id=candidate.id,
                    channel=payload.channel,
                    external_job_id=publication.external_job_id,
                    external_candidate_id=source_item.external_candidate_id,
                    stage=candidate.current_stage,
                    source_status=source_item.raw_profile.get("status"),
                    source_payload=source_item.raw_profile,
                )

        return JobResumeReadySyncResult(
            job_id=job.id,
            channel=payload.channel,
            label_id=payload.label_id,
            pulled_count=len(candidate_items),
            created_count=created_count,
            updated_count=updated_count,
        )

    def _build_connector(self, channel: str):
        if channel == "boss":
            credentials = self._credential_service.resolve_boss_credentials()
            return registry.create(channel, credentials)
        raise ConnectorOperationError(f"Connector settings for channel '{channel}' are not configured")

    def enrich_candidate_metadata(self, limit: int = 5) -> int:
        """后台补全候选人元数据的任务。"""
        # 1. 寻找待补全的候选人
        pending_candidates = self._candidate_repository.list_pending_metadata_enrichment(limit=limit)
        if not pending_candidates:
            return 0
            
        processed_count = 0
        
        # 2. 构造连接器 (仅针对 BOSS)
        connector = self._build_connector("boss")
        
        import time
        import random

        for candidate in pending_candidates:
            try:
                # 间隔久一点，避免安全检测 (5-10s)
                time.sleep(random.uniform(5.0, 10.0))
                
                # 获取画像详情
                detail = connector.fetch_candidate_detail(candidate.raw_profile)
                if detail:
                    # 补全元数据
                    candidate.school = candidate.school or detail.get("school")
                    candidate.degree = candidate.degree or detail.get("degree")
                    candidate.work_experience = candidate.work_experience or detail.get("work_experience")
                    candidate.expected_salary = candidate.expected_salary or detail.get("expected_salary")
                    candidate.latest_company = candidate.latest_company or detail.get("latest_company")
                    
                    # 合并详情原始报文
                    if detail.get("raw_profile"):
                        if not candidate.raw_profile:
                            candidate.raw_profile = {}
                        candidate.raw_profile.update(detail.get("raw_profile"))
                
                # 标记已同步
                self._candidate_repository.mark_metadata_synced(candidate.id)
                logger.debug(
                    "job_service.background_enrich.success candidate_id=%s candidate_name=%s",
                    candidate.id,
                    candidate.name,
                )
                processed_count += 1
            except Exception as e:
                logger.warning(
                    "job_service.background_enrich.failed candidate_id=%s candidate_name=%s error=%s",
                    candidate.id,
                    candidate.name,
                    e,
                )
                # 失败了也记录一下，标记同步过，避免在该批次死循环
                self._candidate_repository.mark_metadata_synced(candidate.id)
                
        return processed_count


def get_job_service(session: Session) -> JobService:
    return JobService(
        JobRepository(session), 
        CandidateRepository(session), 
        JobCandidateRepository(session),
        get_credential_service(session)
    )
