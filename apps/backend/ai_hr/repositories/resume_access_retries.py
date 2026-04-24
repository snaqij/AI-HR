"""候选人附件简历补偿重试仓储。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import CandidateResumeAccessRetry


class ResumeAccessRetryRepository:
    """封装附件简历补偿任务的 upsert、查询和状态推进。"""

    def __init__(self, session: Session):
        self._session = session

    def get_by_candidate(self, candidate_id: str, source_channel: str) -> CandidateResumeAccessRetry | None:
        stmt = select(CandidateResumeAccessRetry).where(
            CandidateResumeAccessRetry.candidate_id == candidate_id,
            CandidateResumeAccessRetry.source_channel == source_channel,
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def get(self, retry_id: str) -> CandidateResumeAccessRetry | None:
        return self._session.get(CandidateResumeAccessRetry, retry_id)

    def list_due(self, *, now: datetime, limit: int) -> list[CandidateResumeAccessRetry]:
        stmt = (
            select(CandidateResumeAccessRetry)
            .where(
                CandidateResumeAccessRetry.attachment_downloaded.is_(False),
                CandidateResumeAccessRetry.next_retry_at.is_not(None),
                CandidateResumeAccessRetry.next_retry_at <= now,
            )
            .order_by(CandidateResumeAccessRetry.next_retry_at.asc())
            .limit(max(1, limit))
        )
        return list(self._session.execute(stmt).scalars().all())

    def upsert_pending(
        self,
        *,
        candidate_id: str,
        source_channel: str,
        external_candidate_id: str,
        request_status: int | None,
        request_sent: bool,
        resume_visible: bool,
        next_retry_at: datetime | None,
        raw_payload: dict,
    ) -> CandidateResumeAccessRetry:
        entity = self.get_by_candidate(candidate_id, source_channel)
        now = datetime.now(UTC).replace(tzinfo=None)
        if entity is None:
            entity = CandidateResumeAccessRetry(
                candidate_id=candidate_id,
                source_channel=source_channel,
                external_candidate_id=external_candidate_id,
                status="pending",
                request_status=request_status,
                request_sent=request_sent,
                resume_visible=resume_visible,
                attachment_downloaded=False,
                retry_count=0,
                last_request_at=now,
                last_checked_at=now,
                next_retry_at=next_retry_at,
                raw_payload=raw_payload or {},
            )
            self._session.add(entity)
        else:
            entity.external_candidate_id = external_candidate_id
            entity.status = "pending"
            entity.request_status = request_status
            entity.request_sent = request_sent
            entity.resume_visible = resume_visible
            entity.last_request_at = now
            entity.last_checked_at = now
            entity.next_retry_at = next_retry_at
            entity.last_error = None
            entity.raw_payload = raw_payload or {}
        self._session.flush()
        return entity

    def mark_checked(
        self,
        entity_id: str,
        *,
        resume_visible: bool,
        next_retry_at: datetime | None,
        raw_payload: dict,
    ) -> CandidateResumeAccessRetry:
        entity = self._session.get(CandidateResumeAccessRetry, entity_id)
        now = datetime.now(UTC).replace(tzinfo=None)
        entity.resume_visible = resume_visible
        entity.last_checked_at = now
        entity.retry_count += 1
        entity.next_retry_at = next_retry_at
        entity.status = "visible" if resume_visible else "pending"
        entity.raw_payload = raw_payload or {}
        entity.last_error = None
        self._session.flush()
        return entity

    def mark_downloaded(self, entity_id: str, *, raw_payload: dict) -> CandidateResumeAccessRetry:
        entity = self._session.get(CandidateResumeAccessRetry, entity_id)
        now = datetime.now(UTC).replace(tzinfo=None)
        entity.status = "downloaded"
        entity.resume_visible = True
        entity.attachment_downloaded = True
        entity.last_checked_at = now
        entity.downloaded_at = now
        entity.next_retry_at = None
        entity.last_error = None
        entity.raw_payload = raw_payload or {}
        self._session.flush()
        return entity

    def mark_failed(self, entity_id: str, *, error_message: str, next_retry_at: datetime | None) -> CandidateResumeAccessRetry:
        entity = self._session.get(CandidateResumeAccessRetry, entity_id)
        now = datetime.now(UTC).replace(tzinfo=None)
        entity.status = "failed"
        entity.last_checked_at = now
        entity.retry_count += 1
        entity.next_retry_at = next_retry_at
        entity.last_error = error_message
        self._session.flush()
        return entity
