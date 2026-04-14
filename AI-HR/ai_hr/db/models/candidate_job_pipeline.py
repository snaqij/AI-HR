"""Candidate-job pipeline persistence model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class CandidateJobPipeline(TimestampMixin, Base):
    """Tracks the end-to-end automation status for a candidate under a job."""

    __tablename__ = "candidate_job_pipeline"
    __table_args__ = (
        Index("uk_candidate_job_pipeline", "candidate_id", "job_id", unique=True),
        Index("idx_candidate_job_pipeline_job", "job_id"),
        Index("idx_candidate_job_pipeline_resume_request_status", "resume_request_status"),
        Index("idx_candidate_job_pipeline_resume_download_status", "resume_download_status"),
        Index("idx_candidate_job_pipeline_evaluation_status", "evaluation_status"),
        Index("idx_candidate_job_pipeline_invitation_status", "invitation_status"),
        Index("idx_candidate_job_pipeline_next_resume_retry_at", "next_resume_retry_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    candidate_id: Mapped[str] = mapped_column(String(36), nullable=False)
    job_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_channel: Mapped[str] = mapped_column(String(64), nullable=False)
    external_candidate_id: Mapped[str] = mapped_column(Text, nullable=False)
    resume_request_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    resume_request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_resume_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_resume_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resume_download_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    resume_attachment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    last_resume_downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evaluation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    latest_evaluation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    last_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invitation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_invited")
    latest_invitation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    last_invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    remark: Mapped[str | None] = mapped_column(String(500), nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
