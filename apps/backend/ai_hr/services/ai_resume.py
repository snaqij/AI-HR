"""AI resume parsing and attachment sync services."""

from __future__ import annotations

import io
import logging
import random
import re
import time
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from typing import Any
from xml.etree import ElementTree as ET

from sqlalchemy.orm import Session

from ..db import models as from_models
from ..connectors.registry import registry
from ..core.config import get_settings
from ..core.exceptions import (
    ConnectorOperationError,
    CredentialsExpiredError,
    InvalidStateError,
    ObjectStorageError,
    ResourceNotFoundError,
)
from ..repositories.ai_observability import AIObservabilityRepository
from ..repositories.ai_runtime import AIRuntimeRepository
from ..repositories.candidates import CandidateRepository
from ..repositories.candidate_job_pipeline import CandidateJobPipelineRepository
from ..repositories.job_candidates import JobCandidateRepository
from ..repositories.resume_attachments import ResumeAttachmentRepository
from ..repositories.resume_access_retries import ResumeAccessRetryRepository
from ..repositories.resume_profiles import ResumeProfileRepository
from ..schemas.ai_resume import (
    CandidateResumeProfileResult,
    ResumeAccessBatchItemResult,
    ResumeAccessBatchSyncRequest,
    ResumeAccessBatchSyncResult,
    ResumeAccessSyncRequest,
    ResumeAccessSyncResult,
    ResumeAttachmentBatchItemResult,
    ResumeAttachmentBatchSyncRequest,
    ResumeAttachmentBatchSyncResult,
    ResumeAttachmentPayload,
    ResumeAttachmentSyncRequest,
    ResumeAttachmentSyncResult,
    ResumeNormalizeRequest,
    ResumeNormalizeResult,
    ResumeParseRequest,
    ResumeParseResult,
    ResumeProfilePayload,
    ResumeRiskItem,
)
from .llm.client import InvokeContext, LLMClient
from .llm.guardrails import GuardrailService
from .llm.prompts import get_prompt_template
from .llm.router import ModelRouter
from .object_storage import MinioResumeStorage, build_resume_storage_key
from .credentials import get_credential_service, CredentialService
PARSER_VERSION_HEURISTIC = "heuristic-v1"
PARSER_VERSION_LLM = "llm-v1"

logger = logging.getLogger(__name__)

_SKILL_KEYWORDS = [
    "python",
    "java",
    "juc",
    "spring",
    "spring boot",
    "spring mvc",
    "mybatis",
    "fastapi",
    "redis",
    "rabbitmq",
    "kafka",
    "mysql",
    "postgresql",
    "pgvector",
    "mcp",
    "rag",
    "sqlalchemy",
    "golang",
    "kubernetes",
    "docker",
    "linux",
]

_EDUCATION_LEVELS = ["博士", "硕士", "本科", "大专", "中专", "高中"]


class AIResumeService:
    """Resume parsing, normalization, and BOSS attachment sync orchestration."""

    def __init__(self, session: Session, credential_service: CredentialService | None = None):
        self._session = session
        self._settings = get_settings()
        self._credential_service = credential_service or get_credential_service(session)
        self._candidate_repository = CandidateRepository(session)
        self._candidate_job_pipeline_repository = CandidateJobPipelineRepository(session)
        self._job_candidate_repository = JobCandidateRepository(session)
        self._resume_attachment_repository = ResumeAttachmentRepository(session)
        self._resume_access_retry_repository = ResumeAccessRetryRepository(session)
        self._resume_repository = ResumeProfileRepository(session)

        runtime_repository = AIRuntimeRepository(session)
        self._runtime_repository = runtime_repository
        observability_repository = AIObservabilityRepository(session)
        self._llm_client = LLMClient(
            router=ModelRouter(runtime_repository),
            guardrail_service=GuardrailService(),
            observability_repository=observability_repository,
        )
        self._resume_storage = self._build_resume_storage()

    def parse_resume(self, payload: ResumeParseRequest) -> ResumeParseResult:
        candidate = self._candidate_repository.get(payload.candidate_id)
        raw_text = (payload.resume_text or candidate.resume_text or "").strip()
        if not raw_text:
            raw_text = self._build_resume_text_fallback(candidate)
            if raw_text:
                candidate.resume_text = raw_text
        if not raw_text:
            raise InvalidStateError(f"Candidate '{payload.candidate_id}' has no resume text to parse")

        parser_version = PARSER_VERSION_HEURISTIC
        parsed, llm_risk_tags = self._parse_with_heuristic(raw_text=raw_text, raw_profile=candidate.raw_profile or {})
        if self._is_llm_enabled():
            llm_parsed, llm_risk_tags = self._parse_with_llm(
                candidate_id=candidate.id,
                raw_text=raw_text,
                raw_profile=candidate.raw_profile or {},
            )
            if llm_parsed:
                parsed = llm_parsed
                parser_version = PARSER_VERSION_LLM

        normalized = self._normalize_profile(parsed)
        confidence = self._estimate_confidence(parsed, raw_text)
        risks = self._detect_risks(normalized, raw_text, extra_risk_tags=llm_risk_tags)

        profile_entity = self._resume_repository.upsert_profile(
            candidate_id=candidate.id,
            raw_text=raw_text,
            parsed_json=parsed,
            normalized_json=normalized,
            parse_status="parsed",
            parser_version=parser_version,
            confidence=confidence,
        )
        risk_entities = self._resume_repository.replace_risks(candidate_id=candidate.id, risks=risks)
        self._session.commit()
        self._session.refresh(profile_entity)
        for risk in risk_entities:
            self._session.refresh(risk)
        return ResumeParseResult(profile=self._to_profile_payload(profile_entity, risk_entities))

    def normalize_resume(self, payload: ResumeNormalizeRequest) -> ResumeNormalizeResult:
        candidate = self._candidate_repository.get(payload.candidate_id)
        profile = self._resume_repository.get_profile(candidate.id)
        raw_text = (candidate.resume_text or "").strip()
        if not raw_text:
            raw_text = self._build_resume_text_fallback(candidate)
            if raw_text:
                candidate.resume_text = raw_text
        if profile is None:
            if not raw_text:
                raise InvalidStateError(f"Candidate '{payload.candidate_id}' has no resume text to normalize")
            parsed, extra_risk_tags = self._parse_with_heuristic(raw_text=raw_text, raw_profile=candidate.raw_profile or {})
            parser_version = PARSER_VERSION_HEURISTIC
        else:
            parsed = dict(profile.parsed_json or {})
            parser_version = profile.parser_version
            extra_risk_tags = []
            if not raw_text:
                raw_text = (profile.raw_text or "").strip()
            if not raw_text:
                raw_text = self._build_resume_text_fallback(candidate)
                if raw_text:
                    candidate.resume_text = raw_text

        normalized = self._normalize_profile(parsed)
        confidence = self._estimate_confidence(parsed, raw_text)
        risks = self._detect_risks(normalized, raw_text, extra_risk_tags=extra_risk_tags)

        profile_entity = self._resume_repository.upsert_profile(
            candidate_id=candidate.id,
            raw_text=raw_text,
            parsed_json=parsed,
            normalized_json=normalized,
            parse_status="normalized",
            parser_version=parser_version,
            confidence=confidence,
        )
        risk_entities = self._resume_repository.replace_risks(candidate_id=candidate.id, risks=risks)
        self._session.commit()
        self._session.refresh(profile_entity)
        for risk in risk_entities:
            self._session.refresh(risk)
        return ResumeNormalizeResult(profile=self._to_profile_payload(profile_entity, risk_entities))

    def get_candidate_resume_profile(self, candidate_id: str) -> CandidateResumeProfileResult:
        self._candidate_repository.get(candidate_id)
        profile = self._resume_repository.get_profile(candidate_id)
        if profile is None:
            raise ResourceNotFoundError(f"Resume profile for candidate '{candidate_id}' was not found")
        risks = self._resume_repository.list_risks(candidate_id)
        return CandidateResumeProfileResult(profile=self._to_profile_payload(profile, risks))

    def sync_resume_attachment(self, payload: ResumeAttachmentSyncRequest) -> ResumeAttachmentSyncResult:
        sync_result = self._sync_resume_attachment_for_candidate(payload.candidate_id)
        return ResumeAttachmentSyncResult(
            attachment=sync_result["attachment"],
            candidate_resume_text_updated=sync_result["candidate_resume_text_updated"],
        )

    def sync_resume_access(self, payload: ResumeAccessSyncRequest) -> ResumeAccessSyncResult:
        result = self._request_resume_access_for_candidate(
            payload.candidate_id,
            sync_attachment_when_ready=payload.sync_attachment_when_ready,
        )
        return ResumeAccessSyncResult(**result)

    def sync_job_resume_access(
        self,
        job_id: str,
        payload: ResumeAccessBatchSyncRequest,
    ) -> ResumeAccessBatchSyncResult:
        job = self._session.get(from_models.Job, job_id)
        if job is None:
            raise ResourceNotFoundError(f"Job '{job_id}' was not found")

        job_candidates, _, _ = self._job_candidate_repository.list_by_job(job_id, limit=10000)
        selected_items = job_candidates
        if payload.candidate_ids:
            allowed_ids = set(payload.candidate_ids)
            selected_items = [item for item in selected_items if item.candidate_id in allowed_ids]
        if payload.limit is not None:
            selected_items = selected_items[: payload.limit]

        results: list[ResumeAccessBatchItemResult] = []
        succeeded_count = 0
        failed_count = 0
        current_requests = self._candidate_job_pipeline_repository.count_requests_today(job_id)
        daily_quota = max(0, int(job.max_daily_resume_requests or 0))
        quota_remaining = max(0, daily_quota - current_requests)

        for item in selected_items:
            if quota_remaining <= 0:
                results.append(
                    ResumeAccessBatchItemResult(
                        candidate_id=item.candidate_id,
                        external_candidate_id=item.external_candidate_id,
                        status="skipped",
                        error_message="quota_exceeded",
                    )
                )
                continue
            try:
                sync_result = self._request_resume_access_for_candidate(
                    item.candidate_id,
                    sync_attachment_when_ready=payload.sync_attachment_when_ready,
                )
                results.append(
                    ResumeAccessBatchItemResult(
                        candidate_id=item.candidate_id,
                        external_candidate_id=item.external_candidate_id,
                        status="synced",
                        request_status=sync_result["request_status"],
                        request_sent=sync_result["request_sent"],
                        resume_visible=sync_result["resume_visible"],
                        attachment_synced=sync_result["attachment_synced"],
                        candidate_resume_text_updated=sync_result["candidate_resume_text_updated"],
                        attachment=sync_result["attachment"],
                        raw_payload=sync_result["raw_payload"],
                    )
                )
                if sync_result["request_sent"]:
                    quota_remaining -= 1
                succeeded_count += 1
            except Exception as exc:  # noqa: BLE001
                results.append(
                    ResumeAccessBatchItemResult(
                        candidate_id=item.candidate_id,
                        external_candidate_id=item.external_candidate_id,
                        status="failed",
                        error_message=str(exc),
                    )
                )
                failed_count += 1
                if payload.stop_on_error:
                    break

        return ResumeAccessBatchSyncResult(
            job_id=job_id,
            total_candidates=len(selected_items),
            succeeded_count=succeeded_count,
            failed_count=failed_count,
            results=results,
        )

    def execute_due_resume_access_retries(self, limit: int | None = None) -> list[dict[str, Any]]:
        now = self._now()
        due_items = self._resume_access_retry_repository.list_due(
            now=now,
            limit=limit or self._settings.resume_access_retry_batch_size,
        )
        results: list[dict[str, Any]] = []
        for item in due_items:
            try:
                results.append(self._process_resume_access_retry(item.id))
            except Exception as exc:  # noqa: BLE001
                self._session.rollback()
                next_retry_at = self._compute_next_resume_retry_at()
                self._resume_access_retry_repository.mark_failed(
                    item.id,
                    error_message=str(exc),
                    next_retry_at=next_retry_at,
                )
                self._session.commit()
                results.append(
                    {
                        "retry_id": item.id,
                        "candidate_id": item.candidate_id,
                        "status": "failed",
                        "error_message": str(exc),
                    }
                )
        return results

    def execute_due_auto_resume_requests(
        self,
        limit: int | None = None,
        *,
        job_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """ Orchestrate 'Smart Bole' automated resume requests based on job thresholds. """
        trace_id = f"auto-resume-{uuid.uuid4().hex[:12]}"
        bootstrapped_count = self._candidate_job_pipeline_repository.bootstrap_pending_auto_request_pipelines(
            job_id=job_id,
            limit=500,
        )
        if bootstrapped_count:
            logger.info(
                "ai_resume.auto_request.bootstrap trace_id=%s bootstrapped_count=%s job_id=%s",
                trace_id,
                bootstrapped_count,
                job_id or "",
            )

        requested_limit = max(1, int(limit or 10))
        active_job_ids = self._candidate_job_pipeline_repository.list_active_auto_request_job_ids(job_id=job_id)
        # Ensure each active job gets a chance in one scheduler cycle (fair polling across jobs).
        effective_limit = max(requested_limit, len(active_job_ids))

        pipelines = self._candidate_job_pipeline_repository.list_pending_auto_requests(
            limit=effective_limit,
            job_id=job_id,
        )
        
        if not pipelines:
            logger.info(
                "ai_resume.auto_request.empty trace_id=%s job_id=%s",
                trace_id,
                job_id or "",
            )
            return []
            
        logger.info(
            "ai_resume.auto_request.scan_start trace_id=%s pending_candidates=%s active_jobs=%s requested_limit=%s effective_limit=%s",
            trace_id,
            len(pipelines),
            len(active_job_ids),
            requested_limit,
            effective_limit,
        )
        results: list[dict[str, Any]] = []
        
        # Cache for job settings and daily counts to avoid redundant queries
        job_cache: dict[str, Any] = {}
        # NEW: Keep track of jobs that hit quota in this run
        reached_quota_job_ids = set()
        processed_somebody = False
        last_request_at_monotonic: float | None = None
        
        for pipeline in pipelines:
            # Immediate circuit-break: if job quota is reached, skip remaining candidates for this job
            if pipeline.job_id in reached_quota_job_ids:
                continue

            try:
                # 1. Get Job Settings
                if pipeline.job_id not in job_cache:
                    job = self._session.get(from_models.Job, pipeline.job_id)
                    if not job or not job.auto_request_resume:
                        continue
                    current_requests = self._candidate_job_pipeline_repository.count_requests_today(job.id)
                    job_cache[job.id] = {
                        "job": job,
                        "current_requests": current_requests,
                        "quota_remaining": job.max_daily_resume_requests - current_requests
                    }
                
                cache = job_cache[pipeline.job_id]
                job = cache["job"]
                
                # 2. Check Daily Quota
                if cache["quota_remaining"] <= 0:
                    logger.info(
                        "ai_resume.auto_request.quota_reached trace_id=%s job_id=%s job_title=%s daily_quota=%s",
                        trace_id,
                        job.id,
                        job.title,
                        job.max_daily_resume_requests,
                    )
                    reached_quota_job_ids.add(pipeline.job_id)
                    continue

                # 3. Fetch Candidate for Threshold Check
                candidate = self._candidate_repository.get(pipeline.candidate_id)
                
                # 4. Filter by Thresholds
                threshold_result = self._meets_thresholds(candidate, job)
                if not threshold_result["passed"]:
                    reason = threshold_result["reason"] or "threshold_not_met"
                    self._candidate_job_pipeline_repository.mark_resume_request_skipped(
                        pipeline.id,
                        reason=reason,
                        payload_patch={
                            "skip_reason_code": threshold_result["code"],
                            "skip_reason_message": reason,
                        },
                    )
                    self._session.commit()
                    continue
                
                # 5. Execute Request
                logger.info(
                    "ai_resume.auto_request.request_start trace_id=%s candidate_id=%s candidate_name=%s job_id=%s job_title=%s",
                    trace_id,
                    candidate.id,
                    candidate.name,
                    job.id,
                    job.title,
                )

                # Throttle outbound resume requests to reduce connector pressure.
                # Keep a long randomized interval for platform risk-control stability.
                if last_request_at_monotonic is not None:
                    elapsed = time.monotonic() - last_request_at_monotonic
                    target_interval_sec = random.uniform(30.0, 70.0)
                    if elapsed < target_interval_sec:
                        time.sleep(target_interval_sec - elapsed)
                
                res = self._request_resume_access_for_candidate(
                    candidate.id,
                    sync_attachment_when_ready=True
                )
                last_request_at_monotonic = time.monotonic()
                logger.info(
                    "ai_resume.auto_request.request_success trace_id=%s candidate_id=%s job_id=%s request_status=%s",
                    trace_id,
                    candidate.id,
                    job.id,
                    res.get("request_status", ""),
                )
                
                cache["quota_remaining"] -= 1
                results.append(res)
                processed_somebody = True
                
            except CredentialsExpiredError as exc:
                self._session.rollback()
                logger.warning(
                    "ai_resume.auto_request.credentials_expired trace_id=%s candidate_id=%s job_id=%s error=%s action=abort_batch",
                    trace_id,
                    pipeline.candidate_id,
                    pipeline.job_id,
                    str(exc),
                )
                # Bubble up so scheduler can handle credential failure once per cycle.
                raise
            except Exception:
                self._session.rollback()
                logger.exception(
                    "ai_resume.auto_request.request_failed trace_id=%s candidate_id=%s job_id=%s",
                    trace_id,
                    pipeline.candidate_id,
                    pipeline.job_id,
                )
                continue
        
        if not processed_somebody and pipelines:
            logger.info(
                "ai_resume.auto_request.no_match trace_id=%s pending_candidates=%s",
                trace_id,
                len(pipelines),
            )
                
        return results

    def _get_degree_rank(self, degree_str: str | None) -> int:
        """ Convert degree string to a numerical rank for comparison. """
        if not degree_str:
            return -1
        
        d = degree_str.strip()
        if "博士" in d or "PhD" in d.upper():
            return 5
        if "硕士" in d or "研究生" in d:
            return 4
        if "本科" in d or "学士" in d:
            return 3
        if "大专" in d or "专科" in d:
            return 2
        if "中专" in d:
            return 1
        if "高中" in d:
            return 0
        return -1

    def _meets_thresholds(self, candidate: from_models.Candidate, job: from_models.Job) -> dict[str, Any]:
        """Check if candidate meets the automated request thresholds."""
        # 1. Degree Check (Fuzzy match)
        if job.min_degree:
            target_rank = self._get_degree_rank(job.min_degree)
            candidate_rank = self._get_degree_rank(candidate.degree)
            if candidate_rank < target_rank:
                message = f"Degree {candidate.degree} < {job.min_degree}"
                logger.debug(
                    "ai_resume.auto_request.skip_degree candidate_id=%s job_id=%s candidate_name=%s reason=%s",
                    candidate.id,
                    job.id,
                    candidate.name,
                    message,
                )
                return {
                    "passed": False,
                    "code": "degree_not_meet",
                    "reason": message,
                }
        
        # 2. Experience Check
        if job.min_experience_years is not None and job.min_experience_years > 0:
            exp_str = candidate.work_experience or ""
            years = 0
            match = re.search(r"(\d+)", exp_str)
            if match:
                val = int(match.group(1))
                if val > 2000: # Graduation year hint
                    years = 0
                else:
                    years = val
            
            if years < job.min_experience_years:
                message = f"Experience {years}y < {job.min_experience_years}y"
                logger.debug(
                    "ai_resume.auto_request.skip_experience candidate_id=%s job_id=%s candidate_name=%s reason=%s",
                    candidate.id,
                    job.id,
                    candidate.name,
                    message,
                )
                return {
                    "passed": False,
                    "code": "experience_not_meet",
                    "reason": message,
                }
                
        return {
            "passed": True,
            "code": None,
            "reason": None,
        }

    def sync_job_resume_attachments(
        self,
        job_id: str,
        payload: ResumeAttachmentBatchSyncRequest,
    ) -> ResumeAttachmentBatchSyncResult:
        job_candidates, _, _ = self._job_candidate_repository.list_by_job(job_id, limit=10000)
        selected_items = job_candidates
        if payload.candidate_ids:
            allowed_ids = set(payload.candidate_ids)
            selected_items = [item for item in selected_items if item.candidate_id in allowed_ids]
        if payload.limit is not None:
            selected_items = selected_items[: payload.limit]

        results: list[ResumeAttachmentBatchItemResult] = []
        succeeded_count = 0
        failed_count = 0

        for item in selected_items:
            try:
                sync_result = self._sync_resume_attachment_for_candidate(item.candidate_id)
                results.append(
                    ResumeAttachmentBatchItemResult(
                        candidate_id=item.candidate_id,
                        external_candidate_id=item.external_candidate_id,
                        status="synced",
                        attachment=sync_result["attachment"],
                        candidate_resume_text_updated=sync_result["candidate_resume_text_updated"],
                    )
                )
                succeeded_count += 1
            except Exception as exc:  # noqa: BLE001
                results.append(
                    ResumeAttachmentBatchItemResult(
                        candidate_id=item.candidate_id,
                        external_candidate_id=item.external_candidate_id,
                        status="failed",
                        error_message=str(exc),
                    )
                )
                failed_count += 1
                if payload.stop_on_error:
                    break

        return ResumeAttachmentBatchSyncResult(
            job_id=job_id,
            total_candidates=len(selected_items),
            succeeded_count=succeeded_count,
            failed_count=failed_count,
            results=results,
        )

    def _sync_resume_attachment_for_candidate(self, candidate_id: str) -> dict[str, Any]:
        candidate = self._candidate_repository.get(candidate_id)
        connector = self._build_connector(candidate.source_channel)
        try:
            result = connector.fetch_resume_attachment(candidate.external_candidate_id, raw_profile=candidate.raw_profile or {})
        except ConnectorOperationError as exc:
            friendly_message = self._to_user_friendly_attachment_sync_error(
                channel=candidate.source_channel,
                raw_error=str(exc),
            )
            logger.warning(
                "resume_attachment_sync_failed candidate_id=%s external_candidate_id=%s channel=%s error=%s",
                candidate.id,
                candidate.external_candidate_id,
                candidate.source_channel,
                str(exc),
                exc_info=True,
            )
            raise InvalidStateError(friendly_message) from exc
        object_storage_meta = self._upload_resume_attachment_to_object_storage(
            candidate_id=candidate.id,
            source_channel=candidate.source_channel,
            file_name=str(result.get("file_name") or "resume.bin"),
            file_sha256=str(result.get("file_sha256") or ""),
            content_type=result.get("content_type"),
            content_bytes=result.get("content_bytes") or b"",
        )
        attachment_source_url = object_storage_meta.get("object_url") or result.get("source_url")
        raw_payload = dict(result.get("raw_payload") or {})
        if object_storage_meta:
            raw_payload["object_storage"] = object_storage_meta
        attachment = self._resume_attachment_repository.upsert(
            candidate_id=candidate.id,
            source_channel=candidate.source_channel,
            external_candidate_id=candidate.external_candidate_id,
            file_name=result["file_name"],
            content_type=result.get("content_type"),
            source_url=attachment_source_url,
            file_size_bytes=int(result["file_size_bytes"]),
            file_sha256=result["file_sha256"],
            content_bytes=result["content_bytes"],
            raw_payload=raw_payload,
        )

        updated_resume_text = False
        resume_text = str(result.get("resume_text") or "").strip()
        if not resume_text:
            resume_text = self._extract_resume_text_from_attachment(
                file_name=str(result.get("file_name") or ""),
                content_type=str(result.get("content_type") or ""),
                content_bytes=result.get("content_bytes") or b"",
            ) or ""
        if result.get("resume_text") or attachment_source_url:
            current_profile = dict(candidate.raw_profile or {})
            current_profile.update(
                {
                    "resume_attachment_synced": True,
                    "resume_attachment_file_name": result["file_name"],
                }
            )
            if attachment_source_url:
                candidate.resume_url = attachment_source_url
            if object_storage_meta:
                current_profile["resume_attachment_object_storage"] = object_storage_meta
            if resume_text:
                candidate.resume_text = resume_text
                updated_resume_text = True
                current_profile["resume_text_source"] = "attachment"
            parsed_email = self._resolve_candidate_email_from_resume(
                resume_text=resume_text,
                raw_profile=current_profile,
            )
            if parsed_email:
                candidate.email = parsed_email
                current_profile["email"] = parsed_email
            candidate.raw_profile = current_profile
        elif resume_text:
            # Even if source_url is absent, preserve extracted text for downstream parse/evaluation.
            candidate.resume_text = resume_text
            updated_resume_text = True
            parsed_email = self._resolve_candidate_email_from_resume(
                resume_text=resume_text,
                raw_profile=candidate.raw_profile or {},
            )
            if parsed_email:
                candidate.email = parsed_email
                profile_patch = dict(candidate.raw_profile or {})
                profile_patch["email"] = parsed_email
                candidate.raw_profile = profile_patch

        for link in self._job_candidate_repository.list_by_candidate(candidate.id):
            pipeline = self._candidate_job_pipeline_repository.ensure(
                candidate_id=candidate.id,
                job_id=link.job_id,
                source_channel=link.channel,
                external_candidate_id=link.external_candidate_id,
                payload={"job_candidate_id": link.id},
            )
            self._candidate_job_pipeline_repository.mark_resume_downloaded(
                pipeline.id,
                resume_attachment_id=attachment.id,
                payload_patch={"resume_attachment_file_name": result["file_name"]},
            )

        self._session.commit()
        self._session.refresh(attachment)
        return {
            "attachment": self._to_attachment_payload(attachment),
            "candidate_resume_text_updated": updated_resume_text,
        }

    def _to_user_friendly_attachment_sync_error(self, *, channel: str, raw_error: str) -> str:
        normalized_channel = str(channel or "").strip().lower()
        raw_text = str(raw_error or "").strip()
        lower_text = raw_text.lower()
        if normalized_channel == "boss":
            if (
                "attachment download is currently unavailable for this candidate" in lower_text
                or "download4boss" in lower_text
                or "no permission to view attachment" in lower_text
                or "invalid candidate identifier" in lower_text
            ):
                return (
                    "暂时无法下载该候选人的附件简历。可能是 BOSS 侧附件权限未开放或附件标识异常。"
                    "请先在 BOSS 聊天页确认可查看附件简历，必要时先执行“申请获取简历”，稍后再重试。"
                )
            if "did not include a downloadable attachment url" in lower_text:
                return "暂时未获取到可下载的附件简历链接，请稍后重试或先在 BOSS 侧申请简历权限。"
        return "简历附件同步失败，请稍后重试。若多次失败，请检查渠道权限配置后再试。"

    def hydrate_resume_text_from_latest_attachment(self, candidate_id: str, *, force_refresh: bool = False) -> bool:
        """Backfill candidate.resume_text/email from latest attachment.

        When force_refresh=True, always prefer latest attachment text for downstream evaluation consistency.
        """
        candidate = self._candidate_repository.get(candidate_id)
        existing_text = (candidate.resume_text or "").strip()
        if existing_text and not force_refresh:
            return False
        attachment = self._resume_attachment_repository.get_latest(candidate_id)
        if attachment is None:
            return False
        extracted = self._extract_resume_text_from_attachment(
            file_name=str(attachment.file_name or ""),
            content_type=str(attachment.content_type or ""),
            content_bytes=attachment.content_bytes or b"",
        )
        if not extracted:
            return False
        updated = False
        if force_refresh or extracted != existing_text:
            candidate.resume_text = extracted
            updated = True
        current_profile = dict(candidate.raw_profile or {})
        current_profile["resume_text_source"] = "attachment_refresh" if force_refresh else "attachment_backfill"
        parsed_email = self._resolve_candidate_email_from_resume(
            resume_text=extracted,
            raw_profile=current_profile,
        )
        if parsed_email:
            if candidate.email != parsed_email:
                candidate.email = parsed_email
                updated = True
            current_profile["email"] = parsed_email
        candidate.raw_profile = current_profile
        self._session.flush()
        return updated

    def _request_resume_access_for_candidate(
        self,
        candidate_id: str,
        *,
        sync_attachment_when_ready: bool,
    ) -> dict[str, Any]:
        candidate = self._candidate_repository.get(candidate_id)
        connector = self._build_connector(candidate.source_channel)
        request_result = connector.request_resume_access(
            candidate.external_candidate_id,
            raw_profile=candidate.raw_profile or {},
        )

        detail = dict(request_result.get("detail") or {})
        raw_payload = dict(request_result.get("raw_payload") or {})
        current_profile = dict(candidate.raw_profile or {})
        current_profile.update(detail)
        current_profile["resume_access_request_status"] = request_result.get("request_status")
        current_profile["resume_access_request_sent"] = request_result.get("request_sent", False)
        current_profile["resume_access_resume_visible"] = request_result.get("resume_visible", False)
        candidate.raw_profile = current_profile

        security_id = request_result.get("security_id")
        if security_id:
            candidate.external_candidate_id = str(security_id)

        attachment_payload = None
        attachment_synced = False
        candidate_resume_text_updated = False
        links = self._job_candidate_repository.list_by_candidate(candidate.id)
        request_sent = bool(request_result.get("request_sent", False))
        resume_visible = bool(request_result.get("resume_visible", False))
        next_retry_at = self._compute_next_resume_retry_at() if request_sent and not attachment_synced else None

        if request_sent:
            self._resume_access_retry_repository.upsert_pending(
                candidate_id=candidate.id,
                source_channel=candidate.source_channel,
                external_candidate_id=candidate.external_candidate_id,
                request_status=request_result.get("request_status"),
                request_sent=request_sent,
                resume_visible=resume_visible,
                next_retry_at=next_retry_at,
                raw_payload=raw_payload,
            )

        for link in links:
            pipeline = self._candidate_job_pipeline_repository.ensure(
                candidate_id=candidate.id,
                job_id=link.job_id,
                source_channel=link.channel,
                external_candidate_id=link.external_candidate_id,
                payload={"job_candidate_id": link.id},
            )
            if resume_visible:
                self._candidate_job_pipeline_repository.mark_resume_visible(
                    pipeline.id,
                    next_retry_at=next_retry_at,
                    payload_patch={
                        "resume_access_request_status": request_result.get("request_status"),
                        "resume_visible": True,
                    },
                )
            elif request_sent:
                self._candidate_job_pipeline_repository.mark_resume_requested(
                    pipeline.id,
                    next_retry_at=next_retry_at,
                    payload_patch={
                        "resume_access_request_status": request_result.get("request_status"),
                        "resume_visible": resume_visible,
                    },
                )
        self._session.commit()

        if sync_attachment_when_ready and resume_visible:
            try:
                sync_result = self._sync_resume_attachment_for_candidate(candidate_id)
                attachment_payload = sync_result["attachment"]
                attachment_synced = True
                candidate_resume_text_updated = sync_result["candidate_resume_text_updated"]
            except Exception:
                retry_entity = self._resume_access_retry_repository.get_by_candidate(candidate.id, candidate.source_channel)
                retry_at = self._compute_next_resume_retry_at()
                if retry_entity is not None:
                    retry_entity.next_retry_at = retry_at
                    retry_entity.resume_visible = True
                    retry_entity.last_error = "resume_attachment_sync_failed"
                    self._session.flush()
                    self._session.commit()
                raise

        if attachment_synced:
            retry_entity = self._resume_access_retry_repository.get_by_candidate(candidate.id, candidate.source_channel)
            if retry_entity is not None:
                self._resume_access_retry_repository.mark_downloaded(
                    retry_entity.id,
                    raw_payload={
                        "request": raw_payload,
                        "downloaded": True,
                    },
                )
                self._session.commit()

        return {
            "candidate_id": candidate_id,
            "external_candidate_id": candidate.external_candidate_id,
            "request_status": request_result.get("request_status"),
            "request_sent": request_sent,
            "resume_visible": resume_visible,
            "attachment_synced": attachment_synced,
            "candidate_resume_text_updated": candidate_resume_text_updated,
            "attachment": attachment_payload,
            "raw_payload": raw_payload,
        }

    def _process_resume_access_retry(self, retry_id: str) -> dict[str, Any]:
        retry_entity = self._resume_access_retry_repository.get(retry_id)
        if retry_entity is None:
            return {"retry_id": retry_id, "status": "missing"}
        candidate = self._candidate_repository.get(retry_entity.candidate_id)
        connector = self._build_connector(candidate.source_channel)
        check_result = connector.check_resume_access(
            candidate.external_candidate_id,
            raw_profile=candidate.raw_profile or {},
        )

        detail = dict(check_result.get("detail") or {})
        current_profile = dict(candidate.raw_profile or {})
        current_profile.update(detail)
        current_profile["resume_access_resume_visible"] = check_result.get("resume_visible", False)
        candidate.raw_profile = current_profile
        security_id = check_result.get("security_id")
        if security_id:
            candidate.external_candidate_id = str(security_id)

        attachment_payload = None
        downloaded = False
        if check_result.get("resume_visible"):
            sync_result = self._sync_resume_attachment_for_candidate(candidate.id)
            attachment_payload = sync_result["attachment"]
            downloaded = True
            self._resume_access_retry_repository.mark_downloaded(
                retry_entity.id,
                raw_payload={
                    "check": check_result.get("raw_payload", {}),
                    "downloaded": True,
                },
            )
        else:
            self._resume_access_retry_repository.mark_checked(
                retry_entity.id,
                resume_visible=False,
                next_retry_at=self._compute_next_resume_retry_at(),
                raw_payload=check_result.get("raw_payload", {}),
            )
        self._session.commit()
        return {
            "retry_id": retry_id,
            "candidate_id": candidate.id,
            "status": "downloaded" if downloaded else "pending",
            "resume_visible": bool(check_result.get("resume_visible", False)),
            "attachment_synced": downloaded,
            "attachment": attachment_payload,
        }

    def _compute_next_resume_retry_at(self):
        return self._now() + timedelta(minutes=max(1, self._settings.resume_access_retry_interval_minutes))

    def _now(self):
        return datetime.now(UTC).replace(tzinfo=None)

    def _parse_with_llm(self, *, candidate_id: str, raw_text: str, raw_profile: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        template = get_prompt_template("resume_parse", "v1")
        prompt = "\n".join([template.system_prompt, template.render(resume_text=raw_text)])
        result = self._llm_client.invoke_json(
            InvokeContext(
                task_key="resume_parse",
                trace_id=str(uuid.uuid4()),
                prompt=prompt,
                entity_type="candidate",
                entity_id=candidate_id,
            )
        )

        if result.fallback_used or result.content.get("error"):
            return None, ["llm_unavailable"]

        content = dict(result.content)
        parsed: dict[str, Any] = {}
        parsed["skills"] = [str(item).strip() for item in content.get("skills", []) if str(item).strip()]
        if content.get("experience_years") is not None:
            try:
                parsed["experience_years"] = float(content["experience_years"])
            except (TypeError, ValueError):
                pass
        if content.get("education_level"):
            parsed["education_level"] = str(content["education_level"])
        if isinstance(content.get("projects"), list):
            parsed["projects"] = content["projects"]
        if "job_hops" in raw_profile:
            try:
                parsed["job_hops"] = int(raw_profile["job_hops"])
            except (TypeError, ValueError):
                pass
        return parsed, [str(item) for item in content.get("risk_tags", [])]

    def _parse_with_heuristic(self, *, raw_text: str, raw_profile: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        lower_text = raw_text.lower()
        parsed: dict[str, Any] = {}

        skills = set()
        for skill in raw_profile.get("skills", []):
            value = str(skill).strip()
            if value:
                skills.add(value)
        for keyword in _SKILL_KEYWORDS:
            if keyword in lower_text:
                skills.add(keyword)
        parsed["skills"] = sorted(skills, key=lambda item: item.lower())

        years = self._extract_years(raw_text)
        if years is not None:
            parsed["experience_years"] = years

        education = self._extract_education(raw_text, raw_profile)
        if education:
            parsed["education_level"] = education

        projects = raw_profile.get("projects")
        if isinstance(projects, list):
            parsed["projects"] = projects
        else:
            parsed["projects"] = self._extract_project_hints(raw_text)

        if "job_hops" in raw_profile:
            try:
                parsed["job_hops"] = int(raw_profile["job_hops"])
            except (TypeError, ValueError):
                pass
        return parsed, []

    def _normalize_profile(self, parsed: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = dict(parsed)

        skills = []
        for item in parsed.get("skills", []):
            text = str(item).strip()
            if not text:
                continue
            canonical = text.lower().replace(" ", "")
            if canonical == "python3":
                canonical = "python"
            skills.append(canonical)
        normalized["skills"] = sorted(set(skills))

        if "experience_years" in parsed:
            try:
                years = float(parsed["experience_years"])
                normalized["experience_years"] = round(max(0.0, years), 1)
            except (TypeError, ValueError):
                normalized.pop("experience_years", None)

        education = str(parsed.get("education_level") or "").strip().lower()
        if education in {"phd", "doctor", "博士"}:
            normalized["education_level"] = "博士"
        elif education in {"master", "硕士", "研究生"}:
            normalized["education_level"] = "硕士"
        elif education in {"bachelor", "本科", "学士"}:
            normalized["education_level"] = "本科"
        elif education in {"college", "大专"}:
            normalized["education_level"] = "大专"
        elif education:
            normalized["education_level"] = str(parsed["education_level"])
        return normalized

    def _detect_risks(self, normalized: dict[str, Any], raw_text: str, extra_risk_tags: list[str] | None = None) -> list[dict[str, str]]:
        risk_map: dict[str, dict[str, str]] = {}

        def add_risk(code: str, level: str, detail: str) -> None:
            risk_map[code] = {"risk_code": code, "risk_level": level, "detail": detail}

        skills = normalized.get("skills", [])
        if not skills:
            add_risk("skills_missing", "medium", "No obvious skill keywords were extracted from the resume.")
        years = normalized.get("experience_years")
        if years is None:
            add_risk("experience_missing", "low", "No clear work experience duration was extracted.")
        job_hops = normalized.get("job_hops")
        if isinstance(job_hops, int) and job_hops >= 4:
            add_risk("job_hops_high", "medium", "Candidate appears to have frequent job changes.")
        if len(raw_text) < 80:
            add_risk("resume_too_short", "low", "Resume text is short and may be incomplete.")

        for tag in extra_risk_tags or []:
            if tag not in risk_map:
                add_risk(tag, "low", f"Model-generated risk tag: {tag}")
        return list(risk_map.values())

    def _estimate_confidence(self, parsed: dict[str, Any], raw_text: str) -> float:
        score = 0.35
        if parsed.get("skills"):
            score += 0.25
        if parsed.get("experience_years") is not None:
            score += 0.2
        if parsed.get("education_level"):
            score += 0.1
        if len(raw_text) >= 120:
            score += 0.1
        return round(min(score, 0.98), 2)

    def _extract_resume_text_from_attachment(self, *, file_name: str, content_type: str, content_bytes: bytes) -> str | None:
        if not content_bytes:
            return None
        ext = file_name.lower().rsplit(".", 1)[-1] if "." in file_name else ""
        ctype = (content_type or "").lower()

        text: str | None = None
        if ext == "pdf" or "pdf" in ctype:
            text = self._extract_pdf_text(content_bytes)
        elif ext == "docx" or "wordprocessingml.document" in ctype:
            text = self._extract_docx_text(content_bytes)
        elif ext in {"txt", "md", "rtf"} or ctype.startswith("text/"):
            text = self._decode_text_bytes(content_bytes)
        else:
            # Best-effort fallback for unknown binary types.
            text = self._extract_pdf_text(content_bytes) or self._extract_docx_text(content_bytes) or self._decode_text_bytes(content_bytes)

        if not text:
            return None
        sanitized = text.replace("\x00", " ").replace("\r", "\n")
        lines = [line.strip() for line in sanitized.split("\n") if line and line.strip()]
        filtered: list[str] = []
        for line in lines:
            # Drop noisy encrypted/token lines that often appear in downloaded PDFs.
            if re.fullmatch(r"[A-Za-z0-9_-]{20,}~{2,}", line):
                continue
            if filtered and filtered[-1] == line:
                continue
            filtered.append(line)
        normalized = "\n".join(filtered)
        return normalized[:120000] if normalized else None

    def _extract_pdf_text(self, data: bytes) -> str | None:
        try:
            import pypdf  # type: ignore
        except Exception:
            return None
        try:
            reader = pypdf.PdfReader(io.BytesIO(data))
            parts = [str(page.extract_text() or "").strip() for page in reader.pages]
            text = "\n".join(part for part in parts if part)
            return text or None
        except Exception:
            return None

    def _extract_docx_text(self, data: bytes) -> str | None:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                xml_bytes = zf.read("word/document.xml")
            root = ET.fromstring(xml_bytes)
            text = "\n".join(chunk.strip() for chunk in root.itertext() if chunk and chunk.strip())
            return text or None
        except Exception:
            return None

    def _decode_text_bytes(self, data: bytes) -> str | None:
        for encoding in ("utf-8", "gb18030", "gbk", "latin-1"):
            try:
                text = data.decode(encoding, errors="ignore").strip()
                if len(text) >= 20:
                    return text
            except Exception:
                continue
        return None

    def _resolve_candidate_email_from_resume(self, *, resume_text: str, raw_profile: dict[str, Any]) -> str | None:
        # 1. Prefer extraction from third-party profile data
        email = self._extract_email_from_profile(raw_profile)
        if email:
            return email
            
        # 2. Heuristic regex extraction (fast and common)
        email = self._extract_email_from_text(resume_text)
        if email:
            return email
            
        # 3. LLM fallback parsing (handles noisy/misaligned/non-standard formats)
        if self._is_llm_enabled() and resume_text.strip():
            # Only sample the start/end of resume text where contact info usually appears
            sample = resume_text[:2000] + "\n...\n" + resume_text[-1000:] if len(resume_text) > 3000 else resume_text
            try:
                from .llm.prompts import PromptTaskKey, get_prompt_template
                from .llm.client import InvokeContext
                import uuid
                template = get_prompt_template(PromptTaskKey.CONTACT_EXTRACT, "v1")
                prompt = "\n".join([template.system_prompt, template.render(text_context=sample)])
                result = self._llm_client.invoke_json(
                    InvokeContext(
                        task_key=PromptTaskKey.CONTACT_EXTRACT,
                        trace_id=str(uuid.uuid4()),
                        prompt=prompt,
                    )
                )
                if not result.fallback_used and result.content.get("email"):
                    llm_email = str(result.content["email"]).strip().lower()
                    if self._looks_like_email(llm_email):
                        return llm_email
            except Exception:
                pass

        return None

    def _extract_email_from_profile(self, raw_profile: dict[str, Any]) -> str | None:
        if not isinstance(raw_profile, dict):
            return None
        # Add support for common Chinese labels
        for key in ("email", "mail", "contact_email", "邮箱", "电子邮箱"):
            value = raw_profile.get(key)
            if isinstance(value, str):
                parsed = self._extract_email_from_text(value)
                if parsed:
                    return parsed
        return None
        for key in ("email", "mail", "contact_email", "閭", "鐢靛瓙閭"):
            value = raw_profile.get(key)
            if isinstance(value, str):
                parsed = self._extract_email_from_text(value)
                if parsed:
                    return parsed
        return None

    def _extract_email_from_text(self, text: str) -> str | None:
        if not text:
            return None
        # Optimize regex: support more suffixes and ambiguous cases
        pattern = r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[A-Za-z]{2,6}\b"
        match = re.search(pattern, text)
        if match:
            return match.group(0).strip().lower()
        
        # Handle obfuscated formats like (at)
        confused = re.search(r"\b[a-zA-Z0-9._%+\-]+(?:\(at\)|@)[a-zA-Z0-9.\-]+\.(?:[A-Za-z]{2,6})\b", text, re.IGNORECASE)
        if confused:
            return confused.group(0).replace("(at)", "@").strip().lower()

        return None

    def _looks_like_email(self, value: str) -> bool:
        return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value.strip()))

    def _build_resume_text_fallback(self, candidate: from_models.Candidate) -> str:
        """Build minimal resume-like text from candidate metadata when resume text is missing."""
        lines: list[str] = []

        def add_line(label: str, value: Any) -> None:
            text = str(value or "").strip()
            if text:
                lines.append(f"{label}: {text}")

        add_line("name", candidate.name)
        add_line("school", candidate.school)
        add_line("degree", candidate.degree)
        add_line("work_experience", candidate.work_experience)
        add_line("latest_company", candidate.latest_company)
        add_line("expected_salary", candidate.expected_salary)

        raw_profile = candidate.raw_profile if isinstance(candidate.raw_profile, dict) else {}
        for key in (
            "skills",
            "skillList",
            "workExperience",
            "education",
            "projectExperience",
            "selfDescription",
            "advantage",
            "positionName",
            "industry",
        ):
            value = raw_profile.get(key)
            if isinstance(value, list):
                joined = "; ".join(str(item).strip() for item in value if str(item).strip())
                add_line(key, joined)
            elif isinstance(value, dict):
                flattened = "; ".join(f"{k}={v}" for k, v in value.items() if str(v).strip())
                add_line(key, flattened)
            else:
                add_line(key, value)
        return "\n".join(lines).strip()

    def _extract_years(self, raw_text: str) -> float | None:
        text = str(raw_text or "")
        lower = text.lower()
        # Fresh graduates/in-school profiles should not be treated as many years of work experience.
        if any(token in text for token in ("应届", "在校", "届生")):
            return 0.0

        patterns = [
            r"(\d+(?:\.\d+)?)\s*年(?:工作)?经验",
            r"工作经验\s*(\d+(?:\.\d+)?)\s*年",
            r"(\d+(?:\.\d+)?)\s*years?\s*(?:of)?\s*experience",
            r"experience\s*[:：]?\s*(\d+(?:\.\d+)?)\s*years?",
        ]
        for pattern in patterns:
            match = re.search(pattern, lower, re.IGNORECASE)
            if not match:
                continue
            try:
                years = float(match.group(1))
            except ValueError:
                continue
            if 0.0 <= years <= 20.0:
                return years
        return None

    def _extract_education(self, raw_text: str, raw_profile: dict[str, Any]) -> str | None:
        for key in ("education", "education_level"):
            value = raw_profile.get(key)
            if value:
                return str(value)
        for level in _EDUCATION_LEVELS:
            if level in raw_text:
                return level
        token = re.search(r"\b(master|bachelor|phd)\b", raw_text, re.IGNORECASE)
        if token:
            return token.group(1)
        return None

    def _extract_project_hints(self, raw_text: str) -> list[dict[str, str]]:
        lines = [line.strip() for line in str(raw_text or "").splitlines() if line and line.strip()]
        if not lines:
            return []

        project_markers = ("项目经验", "项⽬经验", "project experience")
        section_start = -1
        for idx, line in enumerate(lines):
            if any(marker in line.lower() for marker in project_markers):
                section_start = idx
                break

        candidates = lines if section_start < 0 else lines[section_start : min(len(lines), section_start + 80)]
        stop_markers = ("专业技能", "自我评价", "教育背景", "skills", "summary")
        collected: list[str] = []
        for line in candidates:
            lower = line.lower()
            if collected and any(marker in lower for marker in stop_markers):
                break
            if "项目" in line or "项⽬" in line or "project" in lower or "|" in line:
                collected.append(line)

        projects: list[dict[str, str]] = []
        seen: set[str] = set()
        for line in collected:
            name = line.split("|", 1)[0].strip() if "|" in line else line[:40].strip()
            summary = line[:160].strip()
            key = f"{name}|{summary}"
            if not name or key in seen:
                continue
            seen.add(key)
            projects.append({"name": name, "summary": summary})
            if len(projects) >= 5:
                break
        return projects

    def _build_resume_storage(self) -> MinioResumeStorage | None:
        if not self._settings.object_storage_enabled:
            return None
        provider = (self._settings.object_storage_provider or "").strip().lower()
        if provider != "minio":
            raise InvalidStateError(f"Unsupported object storage provider: {provider}")
        return MinioResumeStorage(self._settings)

    def _upload_resume_attachment_to_object_storage(
        self,
        *,
        candidate_id: str,
        source_channel: str,
        file_name: str,
        file_sha256: str,
        content_type: str | None,
        content_bytes: bytes,
    ) -> dict[str, Any]:
        if self._resume_storage is None:
            return {}
        object_key = build_resume_storage_key(
            prefix=self._settings.object_storage_resume_prefix,
            source_channel=source_channel,
            candidate_id=candidate_id,
            file_sha256=file_sha256,
            file_name=file_name,
        )
        try:
            stored = self._resume_storage.upload_resume(
                object_key=object_key,
                content=content_bytes,
                content_type=content_type,
                metadata={
                    "candidate-id": candidate_id,
                    "source-channel": source_channel,
                    "file-sha256": file_sha256,
                },
            )
            return {
                "provider": stored.provider,
                "bucket": stored.bucket,
                "object_key": stored.object_key,
                "object_url": stored.object_url,
                "etag": stored.etag,
            }
        except ObjectStorageError as exc:
            if self._settings.object_storage_required:
                raise
            logger.warning(
                "Resume attachment upload to object storage failed, fallback to DB blob only. "
                "candidate_id=%s channel=%s error=%s",
                candidate_id,
                source_channel,
                exc,
            )
            return {}

    def _build_connector(self, channel: str):
        if channel == "boss":
            credentials = self._credential_service.resolve_boss_credentials()
            return registry.create(channel, credentials)
        raise ConnectorOperationError(f"Connector '{channel}' is not configured")

    def _to_profile_payload(self, profile, risks) -> ResumeProfilePayload:
        return ResumeProfilePayload(
            candidate_id=profile.candidate_id,
            raw_text=profile.raw_text or "",
            parse_status=profile.parse_status,
            parser_version=profile.parser_version,
            confidence=profile.confidence,
            parsed_profile=profile.parsed_json or {},
            normalized_profile=profile.normalized_json or {},
            risks=[ResumeRiskItem(risk_code=item.risk_code, risk_level=item.risk_level, detail=item.detail) for item in risks],
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )

    def _to_attachment_payload(self, attachment) -> ResumeAttachmentPayload:
        object_storage = dict((attachment.raw_payload or {}).get("object_storage") or {})
        return ResumeAttachmentPayload(
            candidate_id=attachment.candidate_id,
            source_channel=attachment.source_channel,
            external_candidate_id=attachment.external_candidate_id,
            file_name=attachment.file_name,
            content_type=attachment.content_type,
            source_url=attachment.source_url,
            file_size_bytes=attachment.file_size_bytes,
            file_sha256=attachment.file_sha256,
            object_storage_provider=object_storage.get("provider"),
            object_storage_bucket=object_storage.get("bucket"),
            object_storage_key=object_storage.get("object_key"),
            object_storage_url=object_storage.get("object_url"),
            last_synced_at=attachment.last_synced_at,
            created_at=attachment.created_at,
            updated_at=attachment.updated_at,
        )

    def _is_llm_enabled(self) -> bool:
        return self._runtime_repository.is_feature_enabled(
            feature_key="ai_resume_llm",
            default_enabled=self._settings.ai_resume_llm_enabled,
        )


def get_ai_resume_service(session: Session) -> AIResumeService:
    return AIResumeService(session, get_credential_service(session))
