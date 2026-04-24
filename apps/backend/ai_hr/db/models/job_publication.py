"""岗位发布记录持久化模型。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin

if TYPE_CHECKING:
    from .job import Job
    from .job_candidate import JobCandidate


class JobPublication(TimestampMixin, Base):
    """岗位在渠道侧的发布状态与回写记录。"""

    __tablename__ = "job_publications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    external_job_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    response_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    applicant_sync_cursor: Mapped[str | None] = mapped_column(String(255), nullable=True)

    job: Mapped["Job"] = relationship(back_populates="publications")
    job_candidates: Mapped[list["JobCandidate"]] = relationship("JobCandidate", back_populates="publication")
