"""附件简历仓储实现。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import CandidateResumeAttachment


class ResumeAttachmentRepository:
    """封装附件简历的 upsert 与查询。"""

    def __init__(self, session: Session):
        self._session = session

    def get_latest(self, candidate_id: str) -> CandidateResumeAttachment | None:
        stmt = (
            select(CandidateResumeAttachment)
            .where(CandidateResumeAttachment.candidate_id == candidate_id)
            .order_by(CandidateResumeAttachment.last_synced_at.desc())
            .limit(1)
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def upsert(
        self,
        *,
        candidate_id: str,
        source_channel: str,
        external_candidate_id: str,
        file_name: str,
        content_type: str | None,
        source_url: str | None,
        file_size_bytes: int,
        file_sha256: str,
        content_bytes: bytes,
        raw_payload: dict,
    ) -> CandidateResumeAttachment:
        stmt = select(CandidateResumeAttachment).where(
            CandidateResumeAttachment.candidate_id == candidate_id,
            CandidateResumeAttachment.source_channel == source_channel,
        )
        entity = self._session.execute(stmt).scalar_one_or_none()
        now = datetime.now(UTC).replace(tzinfo=None)
        if entity is None:
            entity = CandidateResumeAttachment(
                candidate_id=candidate_id,
                source_channel=source_channel,
                external_candidate_id=external_candidate_id,
                file_name=file_name,
                content_type=content_type,
                source_url=source_url,
                file_size_bytes=file_size_bytes,
                file_sha256=file_sha256,
                content_bytes=content_bytes,
                last_synced_at=now,
                raw_payload=raw_payload or {},
            )
            self._session.add(entity)
        else:
            entity.file_name = file_name
            entity.content_type = content_type
            entity.source_url = source_url
            entity.file_size_bytes = file_size_bytes
            entity.file_sha256 = file_sha256
            entity.content_bytes = content_bytes
            entity.last_synced_at = now
            entity.raw_payload = raw_payload or {}
        self._session.flush()
        return entity
