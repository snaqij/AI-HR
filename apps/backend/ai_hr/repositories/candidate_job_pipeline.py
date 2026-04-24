"""Repository for candidate-job automation pipeline records."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.exceptions import InvalidStateError, ResourceNotFoundError
from ..db.models import Candidate, CandidateJobPipeline, Job, JobCandidate
from .workspace_scope import get_workspace_id


class CandidateJobPipelineRepository:
    """Encapsulates lifecycle reads/writes for candidate-job pipeline state."""

    def __init__(self, session: Session):
        self._session = session

    def get(self, pipeline_id: str) -> CandidateJobPipeline:
        workspace_id = get_workspace_id(self._session)
        if workspace_id:
            entity = self._session.execute(
                select(CandidateJobPipeline).where(
                    CandidateJobPipeline.id == pipeline_id,
                    CandidateJobPipeline.workspace_id == workspace_id,
                )
            ).scalar_one_or_none()
        else:
            entity = self._session.get(CandidateJobPipeline, pipeline_id)
        if entity is None:
            raise ResourceNotFoundError(f"Candidate job pipeline '{pipeline_id}' was not found")
        return entity

    def get_by_candidate_job(self, *, candidate_id: str, job_id: str) -> CandidateJobPipeline | None:
        stmt = select(CandidateJobPipeline).where(
            CandidateJobPipeline.candidate_id == candidate_id,
            CandidateJobPipeline.job_id == job_id,
        )
        workspace_id = get_workspace_id(self._session)
        if workspace_id:
            stmt = stmt.where(CandidateJobPipeline.workspace_id == workspace_id)
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
            workspace_id = get_workspace_id(self._session)
            entity = CandidateJobPipeline(
                workspace_id=workspace_id,
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
        workspace_id = get_workspace_id(self._session)
        if workspace_id:
            stmt = stmt.where(CandidateJobPipeline.workspace_id == workspace_id)
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
        workspace_id = get_workspace_id(self._session)
        if workspace_id:
            stmt = stmt.where(CandidateJobPipeline.workspace_id == workspace_id)
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

    def mark_resume_visible(
        self,
        pipeline_id: str,
        *,
        next_retry_at: datetime | None,
        payload_patch: dict | None = None,
    ) -> CandidateJobPipeline:
        entity = self.get(pipeline_id)
        now = datetime.now(UTC).replace(tzinfo=None)
        entity.resume_request_status = "visible"
        if entity.last_resume_requested_at is None:
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
        
        # Base query
        base_stmt = (
            select(CandidateJobPipeline)
            .join(Job, CandidateJobPipeline.job_id == Job.id)
            .where(
                Job.auto_request_resume.is_(True),
                CandidateJobPipeline.resume_request_status == "pending",
            )
        )
        workspace_id = get_workspace_id(self._session)
        if workspace_id:
            base_stmt = base_stmt.where(CandidateJobPipeline.workspace_id == workspace_id)

        if job_id:
            stmt = base_stmt.where(CandidateJobPipeline.job_id == job_id).order_by(CandidateJobPipeline.created_at.desc()).limit(safe_limit)
            return list(self._session.execute(stmt).scalars().all())

        # Fair scheduling: find all job IDs that still have pending candidates
        jobs_stmt = (
            select(Job.id)
            .join(CandidateJobPipeline, CandidateJobPipeline.job_id == Job.id)
            .where(
                Job.auto_request_resume.is_(True),
                CandidateJobPipeline.resume_request_status == "pending",
            )
            .distinct()
        )
        workspace_id = get_workspace_id(self._session)
        if workspace_id:
            jobs_stmt = jobs_stmt.where(CandidateJobPipeline.workspace_id == workspace_id)
        active_job_ids = list(self._session.execute(jobs_stmt).scalars().all())
        
        if not active_job_ids:
            return []
            
        # Fetch a bounded number of candidates per job
        all_candidates_by_job: dict[str, list[CandidateJobPipeline]] = {}
        for jid in active_job_ids:
            # Pull enough candidates per job to fill the batch if other jobs are empty
            job_stmt = base_stmt.where(CandidateJobPipeline.job_id == jid).order_by(CandidateJobPipeline.created_at.desc()).limit(safe_limit)
            all_candidates_by_job[jid] = list(self._session.execute(job_stmt).scalars().all())

        # Interleave results in round-robin order
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

    def list_active_auto_request_job_ids(self, *, job_id: str | None = None) -> list[str]:
        """List job ids that currently have pending auto-request candidates."""
        jobs_stmt = (
            select(Job.id)
            .join(CandidateJobPipeline, CandidateJobPipeline.job_id == Job.id)
            .where(
                Job.auto_request_resume.is_(True),
                CandidateJobPipeline.resume_request_status == "pending",
            )
            .distinct()
        )
        workspace_id = get_workspace_id(self._session)
        if workspace_id:
            jobs_stmt = jobs_stmt.where(CandidateJobPipeline.workspace_id == workspace_id)
        if job_id:
            jobs_stmt = jobs_stmt.where(Job.id == job_id)
        return list(self._session.execute(jobs_stmt).scalars().all())

    def bootstrap_pending_auto_request_pipelines(
        self,
        *,
        job_id: str | None = None,
        limit: int = 300,
    ) -> int:
        """Create missing pending pipelines from job-candidate links for auto-enabled jobs."""
        safe_limit = max(1, int(limit))
        stmt = (
            select(JobCandidate)
            .join(Job, JobCandidate.job_id == Job.id)
            .outerjoin(
                CandidateJobPipeline,
                (CandidateJobPipeline.job_id == JobCandidate.job_id)
                & (CandidateJobPipeline.candidate_id == JobCandidate.candidate_id),
            )
            .where(
                Job.auto_request_resume.is_(True),
                CandidateJobPipeline.id.is_(None),
            )
            .order_by(JobCandidate.last_synced_at.desc())
            .limit(safe_limit)
        )
        workspace_id = get_workspace_id(self._session)
        if workspace_id:
            stmt = stmt.where(Job.workspace_id == workspace_id)
        if job_id:
            stmt = stmt.where(JobCandidate.job_id == job_id)

        links = list(self._session.execute(stmt).scalars().all())
        if not links:
            return 0

        created = 0
        for link in links:
            self.ensure(
                candidate_id=link.candidate_id,
                job_id=link.job_id,
                source_channel=link.channel or "boss",
                external_candidate_id=link.external_candidate_id,
                payload={
                    "bootstrapped_from_job_candidate": True,
                    "job_candidate_id": link.id,
                },
            )
            created += 1
        self._session.flush()
        return created

    def count_requests_today(self, job_id: str) -> int:
        """Count how many resume requests were sent today for a job."""
        now = datetime.now(UTC).replace(tzinfo=None)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = (
            select(func.coalesce(func.sum(CandidateJobPipeline.resume_request_count), 0))
            .where(
                CandidateJobPipeline.job_id == job_id,
                CandidateJobPipeline.last_resume_requested_at >= start_of_day,
                CandidateJobPipeline.resume_request_count > 0,
            )
        )
        workspace_id = get_workspace_id(self._session)
        if workspace_id:
            stmt = stmt.where(CandidateJobPipeline.workspace_id == workspace_id)
        return int(self._session.execute(stmt).scalar() or 0)

    def _merge_payload(self, entity: CandidateJobPipeline, payload_patch: dict | None) -> None:
        if not payload_patch:
            return
        merged = dict(entity.payload or {})
        merged.update(payload_patch)
        entity.payload = merged

    def _assert_candidate_exists(self, candidate_id: str) -> None:
        stmt = select(Candidate).where(Candidate.id == candidate_id)
        workspace_id = get_workspace_id(self._session)
        if workspace_id:
            stmt = stmt.where(Candidate.workspace_id == workspace_id)
        if self._session.execute(stmt).scalar_one_or_none() is None:
            raise ResourceNotFoundError(f"Candidate '{candidate_id}' was not found")

    def _assert_job_exists(self, job_id: str) -> None:
        stmt = select(Job).where(Job.id == job_id)
        workspace_id = get_workspace_id(self._session)
        if workspace_id:
            stmt = stmt.where(Job.workspace_id == workspace_id)
        if self._session.execute(stmt).scalar_one_or_none() is None:
            raise ResourceNotFoundError(f"Job '{job_id}' was not found")
