"""候选人附件简历获取补偿重试模型。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin


class CandidateResumeAccessRetry(TimestampMixin, Base):
    """记录已发起简历请求但尚未完成下载的候选人补偿任务。"""

    __tablename__ = "candidate_resume_access_retries"
    __table_args__ = (
        UniqueConstraint("candidate_id", "source_channel", name="uq_candidate_resume_access_retry_candidate_source"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    candidate_id: Mapped[str] = mapped_column(String(36), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True)
    source_channel: Mapped[str] = mapped_column(String(64), nullable=False)
    external_candidate_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    request_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resume_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attachment_downloaded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_request_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    candidate = relationship("Candidate", back_populates="resume_access_retries")
