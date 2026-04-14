"""Repository for candidate-job automation pipeline records."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.exceptions import InvalidStateError, ResourceNotFoundError
from ..db.models import Candidate, CandidateJobPipeline, Job


class CandidateJobPipelineRepository:
    """Encapsulates lifecycle reads/writes for candidate-job pipeline state."""

    def __init__(self, session: Session):
        self._session = session

    def get(self, pipeline_id: str) -> CandidateJobPipeline:
        entity = self._session.get(CandidateJobPipeline, pipeline_id)
        if entity is None:
            raise ResourceNotFoundError(f"Candidate job pipeline '{pipeline_id}' was not found")
        return entity

    def get_by_candidate_job(self, *, candidate_id: str, job_id: str) -> CandidateJobPipeline | None:
        stmt = select(CandidateJobPipeline).where(
            CandidateJobPipeline.candidate_id == candidate_id,
            CandidateJobPipeline.job_id == job_id,
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def ensure(
        self,
        *,
        candidate_id: str,
        job_id: str,
        source_channel: str,
        external_candidate_id: str,
        payload: dict | None = None,
    ) -> CandidateJobPipeline:
        self._assert_candidate_exists(candidate_id)
        self._assert_job_exists(job_id)
        entity = self.get_by_candidate_job(candidate_id=candidate_id, job_id=job_id)
        if entity is None:
            entity = CandidateJobPipeline(
                candidate_id=candidate_id,
                job_id=job_id,
                source_channel=source_channel,
                external_candidate_id=external_candidate_id,
                payload=payload or {},
            )
            self._session.add(entity)
        else:
            entity.source_channel = source_channel
            entity.external_candidate_id = external_candidate_id
            if payload is not None:
                entity.payload = payload
        self._session.flush()
        return entity

    def list_by_status(
        self,
        *,
        evaluation_status: str | None = None,
        invitation_status: str | None = None,
        resume_download_status: str | None = None,
        limit: int = 100,
    ) -> list[CandidateJobPipeline]:
        stmt = select(CandidateJobPipeline)
        if evaluation_status is not None:
            stmt = stmt.where(CandidateJobPipeline.evaluation_status == evaluation_status)
        if invitation_status is not None:
            stmt = stmt.where(CandidateJobPipeline.invitation_status == invitation_status)
        if resume_download_status is not None:
            stmt = stmt.where(CandidateJobPipeline.resume_download_status == resume_download_status)
        stmt = stmt.order_by(CandidateJobPipeline.updated_at.asc()).limit(max(1, limit))
        return list(self._session.execute(stmt).scalars().all())

    def list_due_resume_retry(self, *, now: datetime, limit: int = 100) -> list[CandidateJobPipeline]:
        stmt = (
            select(CandidateJobPipeline)
            .where(
                CandidateJobPipeline.resume_download_status != "downloaded",
                CandidateJobPipeline.next_resume_retry_at.is_not(None),
                CandidateJobPipeline.next_resume_retry_at <= now,
            )
            .order_by(CandidateJobPipeline.next_resume_retry_at.asc())
            .limit(max(1, limit))
        )
        return list(self._session.execute(stmt).scalars().all())

    def mark_resume_requested(
        self,
        pipeline_id: str,
        *,
        next_retry_at: datetime | None,
        payload_patch: dict | None = None,
    ) -> CandidateJobPipeline:
        entity = self.get(pipeline_id)
        now = datetime.now(UTC).replace(tzinfo=None)
        entity.resume_request_status = "requested"
        entity.resume_request_count += 1
        entity.last_resume_requested_at = now
        entity.next_resume_retry_at = next_retry_at
        self._merge_payload(entity, payload_patch)
        self._session.flush()
        return entity

    def mark_resume_request_skipped(
        self,
        pipeline_id: str,
        *,
        reason: str,
        payload_patch: dict | None = None,
    ) -> CandidateJobPipeline:
        entity = self.get(pipeline_id)
        entity.resume_request_status = "skipped"
        entity.next_resume_retry_at = None
        patch = {"last_skip": {"stage": "resume_request", "reason": reason}}
        if payload_patch:
            patch.update(payload_patch)
        self._merge_payload(entity, patch)
        self._session.flush()
        return entity

    def mark_resume_downloaded(
        self,
        pipeline_id: str,
        *,
        resume_attachment_id: str,
        payload_patch: dict | None = None,
    ) -> CandidateJobPipeline:
        entity = self.get(pipeline_id)
        now = datetime.now(UTC).replace(tzinfo=None)
        entity.resume_request_status = "visible"
        entity.resume_download_status = "downloaded"
        entity.resume_attachment_id = resume_attachment_id
        entity.last_resume_downloaded_at = now
        entity.next_resume_retry_at = None
        self._merge_payload(entity, payload_patch)
        self._session.flush()
        return entity

    def mark_evaluated(
        self,
        pipeline_id: str,
        *,
        evaluation_id: str,
        payload_patch: dict | None = None,
    ) -> CandidateJobPipeline:
        entity = self.get(pipeline_id)
        now = datetime.now(UTC).replace(tzinfo=None)
        entity.evaluation_status = "completed"
        entity.latest_evaluation_id = evaluation_id
        entity.last_evaluated_at = now
        self._merge_payload(entity, payload_patch)
        self._session.flush()
        return entity

    def mark_invited(
        self,
        pipeline_id: str,
        *,
        invitation_id: str,
        payload_patch: dict | None = None,
    ) -> CandidateJobPipeline:
        entity = self.get(pipeline_id)
        now = datetime.now(UTC).replace(tzinfo=None)
        entity.invitation_status = "invited"
        entity.latest_invitation_id = invitation_id
        entity.last_invited_at = now
        self._merge_payload(entity, payload_patch)
        self._session.flush()
        return entity

    def mark_failed(
        self,
        pipeline_id: str,
        *,
        stage: str,
        reason: str,
        next_retry_at: datetime | None = None,
    ) -> CandidateJobPipeline:
        entity = self.get(pipeline_id)
        if stage == "resume_request":
            entity.resume_request_status = "failed"
            entity.next_resume_retry_at = next_retry_at
        elif stage == "resume_download":
            entity.resume_download_status = "failed"
            entity.next_resume_retry_at = next_retry_at
        elif stage == "evaluation":
            entity.evaluation_status = "failed"
        elif stage == "invitation":
            entity.invitation_status = "failed"
        else:
            raise InvalidStateError(f"Unsupported pipeline stage '{stage}'")
        self._merge_payload(entity, {"last_failure": {"stage": stage, "reason": reason}})
        self._session.flush()
        return entity

    def list_pending_auto_requests(self, *, limit: int = 10, job_id: str | None = None) -> list[CandidateJobPipeline]:
        """Return pending auto-request pipelines with cross-job fairness."""
        safe_limit = max(1, int(limit))
        
        # 基础查询语句
        base_stmt = (
            select(CandidateJobPipeline)
            .join(Job, CandidateJobPipeline.job_id == Job.id)
            .join(Candidate, CandidateJobPipeline.candidate_id == Candidate.id)
            .where(
                Job.auto_request_resume.is_(True),
                CandidateJobPipeline.resume_request_status == "pending",
                Candidate.metadata_synced_at.is_not(None),
            )
        )

        if job_id:
            stmt = base_stmt.where(CandidateJobPipeline.job_id == job_id).order_by(CandidateJobPipeline.created_at.desc()).limit(safe_limit)
            return list(self._session.execute(stmt).scalars().all())

        # 公平调度策略：先找出所有有待处理候选人的岗位 ID
        jobs_stmt = (
            select(Job.id)
            .join(CandidateJobPipeline, CandidateJobPipeline.job_id == Job.id)
            .join(Candidate, CandidateJobPipeline.candidate_id == Candidate.id)
            .where(
                Job.auto_request_resume.is_(True),
                CandidateJobPipeline.resume_request_status == "pending",
                Candidate.metadata_synced_at.is_not(None),
            )
            .distinct()
        )
        active_job_ids = list(self._session.execute(jobs_stmt).scalars().all())
        
        if not active_job_ids:
            return []
            
        # 针对每个岗位，分别拉取一定数量的候选人
        all_candidates_by_job: dict[str, list[CandidateJobPipeline]] = {}
        for jid in active_job_ids:
            # 每个岗位拉取足够填满整个批次的候选项（以防其他岗位没数据）
            job_stmt = base_stmt.where(CandidateJobPipeline.job_id == jid).order_by(CandidateJobPipeline.created_at.desc()).limit(safe_limit)
            all_candidates_by_job[jid] = list(self._session.execute(job_stmt).scalars().all())

        # 交替混编 (Round-robin)
        selected: list[CandidateJobPipeline] = []
        while len(selected) < safe_limit:
            picked_anything = False
            for jid in active_job_ids:
                if all_candidates_by_job.get(jid):
                    selected.append(all_candidates_by_job[jid].pop(0))
                    picked_anything = True
                    if len(selected) >= safe_limit:
                        break
            if not picked_anything:
                break
        
        return selected

    def count_requests_today(self, job_id: str) -> int:
        """Count how many resume requests were sent today for a job."""
        now = datetime.now(UTC).replace(tzinfo=None)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = (
            select(CandidateJobPipeline)
            .where(
                CandidateJobPipeline.job_id == job_id,
                CandidateJobPipeline.last_resume_requested_at >= start_of_day,
            )
        )
        # Simplified count for execute
        return len(list(self._session.execute(stmt).scalars().all()))

    def _merge_payload(self, entity: CandidateJobPipeline, payload_patch: dict | None) -> None:
        if not payload_patch:
            return
        merged = dict(entity.payload or {})
        merged.update(payload_patch)
        entity.payload = merged

    def _assert_candidate_exists(self, candidate_id: str) -> None:
        if self._session.get(Candidate, candidate_id) is None:
            raise ResourceNotFoundError(f"Candidate '{candidate_id}' was not found")

    def _assert_job_exists(self, job_id: str) -> None:
        if self._session.get(Job, job_id) is None:
            raise ResourceNotFoundError(f"Job '{job_id}' was not found")
