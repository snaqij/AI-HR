"""候选人附件简历持久化模型。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin

_binary_type = LargeBinary().with_variant(mysql.LONGBLOB, "mysql")


class CandidateResumeAttachment(TimestampMixin, Base):
    """保存从外部渠道下载的附件简历原件与元数据。"""

    __tablename__ = "candidate_resume_attachments"
    __table_args__ = (
        UniqueConstraint("candidate_id", "source_channel", name="uq_resume_attachment_candidate_source"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    candidate_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_channel: Mapped[str] = mapped_column(String(64), nullable=False)
    external_candidate_id: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(nullable=False, default=0)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content_bytes: Mapped[bytes] = mapped_column(_binary_type, nullable=False)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    candidate = relationship("Candidate", back_populates="resume_attachments")
