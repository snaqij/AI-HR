"""面试仓储实现。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.exceptions import ResourceNotFoundError
from ..db.models import Interview, JobShortlist


class InterviewRepository:
    """封装面试记录持久化能力。"""

    def __init__(self, session: Session):
        self._session = session

    def create(
        self,
        *,
        candidate_id: str,
        job_id: str,
        channel: str,
        scheduled_at: datetime | None,
        meeting_link: str | None,
        target_headcount: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Interview:
        interview = Interview(
            candidate_id=candidate_id,
            job_id=job_id,
            channel=channel,
            status="pending",
            scheduled_at=scheduled_at,
            meeting_link=meeting_link,
            target_headcount=target_headcount,
            payload=payload or {},
        )
        self._session.add(interview)
        self._session.commit()
        self._session.refresh(interview)
        return interview

    def find_latest_by_job_candidate(self, *, job_id: str, candidate_id: str) -> Interview | None:
        stmt = (
            select(Interview)
            .where(Interview.job_id == job_id, Interview.candidate_id == candidate_id)
            .order_by(Interview.created_at.desc())
        )
        return self._session.execute(stmt).scalars().first()

    def list_shortlist(self, job_id: str) -> list[JobShortlist]:
        stmt = select(JobShortlist).where(JobShortlist.job_id == job_id).order_by(JobShortlist.rank.asc())
        return list(self._session.execute(stmt).scalars().all())

    def count_distinct_candidates_with_interview(self, job_id: str) -> int:
        stmt = select(func.count(func.distinct(Interview.candidate_id))).where(Interview.job_id == job_id)
        return int(self._session.execute(stmt).scalar_one() or 0)

    def get_progress_stats(self, job_id: str) -> dict[str, int]:
        sent_stmt = select(func.count(Interview.id)).where(Interview.job_id == job_id)
        sent = int(self._session.execute(sent_stmt).scalar_one() or 0)

        success_stmt = select(func.count(Interview.id)).where(
            Interview.job_id == job_id,
            Interview.status.in_(["scheduled", "confirmed"]),
        )
        success = int(self._session.execute(success_stmt).scalar_one() or 0)

        failed_stmt = select(func.count(Interview.id)).where(
            Interview.job_id == job_id,
            Interview.status.in_(["dispatch_failed", "sync_failed"]),
        )
        failed = int(self._session.execute(failed_stmt).scalar_one() or 0)

        pending_stmt = select(func.count(Interview.id)).where(
            Interview.job_id == job_id,
            Interview.status.in_(["pending", "scheduled"]),
        )
        pending_confirmation = int(self._session.execute(pending_stmt).scalar_one() or 0)

        target_stmt = select(func.max(Interview.target_headcount)).where(Interview.job_id == job_id)
        total_target = int(self._session.execute(target_stmt).scalar_one() or 0)
        if total_target <= 0:
            total_target = sent

        return {
            "total_target": total_target,
            "sent": sent,
            "success": success,
            "failed": failed,
            "pending_confirmation": pending_confirmation,
        }

    def get(self, interview_id: str) -> Interview:
        stmt = select(Interview).where(Interview.id == interview_id)
        interview = self._session.execute(stmt).scalar_one_or_none()
        if interview is None:
            raise ResourceNotFoundError(f"Interview '{interview_id}' was not found")
        return interview

    def update_dispatch_result(
        self,
        interview_id: str,
        *,
        status: str,
        external_interview_id: str | None,
        payload: dict[str, Any] | None = None,
    ) -> Interview:
        interview = self.get(interview_id)
        interview.status = status
        if external_interview_id:
            interview.external_interview_id = external_interview_id
        merged_payload = dict(interview.payload or {})
        merged_payload["dispatch"] = payload or {}
        merged_payload["dispatch_at"] = datetime.now(UTC).replace(tzinfo=None).isoformat()
        interview.payload = merged_payload
        self._session.commit()
        self._session.refresh(interview)
        return interview

    def update_sync_status(self, interview_id: str, *, status: str, payload: dict[str, Any] | None = None) -> Interview:
        interview = self.get(interview_id)
        interview.status = status
        merged_payload = dict(interview.payload or {})
        merged_payload["sync"] = payload or {}
        merged_payload["sync_at"] = datetime.now(UTC).replace(tzinfo=None).isoformat()
        interview.payload = merged_payload
        self._session.commit()
        self._session.refresh(interview)
        return interview

    def update_latest_status_by_job_candidate(
        self,
        *,
        job_id: str,
        candidate_id: str,
        status: str,
        payload_patch: dict[str, Any] | None = None,
    ) -> Interview | None:
        interview = self.find_latest_by_job_candidate(job_id=job_id, candidate_id=candidate_id)
        if interview is None:
            return None
        interview.status = status
        merged_payload = dict(interview.payload or {})
        if payload_patch:
            merged_payload.update(payload_patch)
        interview.payload = merged_payload
        self._session.commit()
        self._session.refresh(interview)
        return interview
