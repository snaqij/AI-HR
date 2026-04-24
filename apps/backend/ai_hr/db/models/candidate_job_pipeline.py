"""Candidate-job pipeline persistence model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class CandidateJobPipeline(TimestampMixin, Base):
    """Tracks the end-to-end automation status for a candidate under a job."""

    __tablename__ = "candidate_job_pipeline"
    __table_args__ = (
        Index("uk_candidate_job_pipeline", "candidate_id", "job_id", unique=True),
        Index("idx_candidate_job_pipeline_job", "job_id"),
        Index("idx_candidate_job_pipeline_workspace_id", "workspace_id"),
        Index("idx_candidate_job_pipeline_resume_request_status", "resume_request_status"),
        Index("idx_candidate_job_pipeline_resume_download_status", "resume_download_status"),
        Index("idx_candidate_job_pipeline_evaluation_status", "evaluation_status"),
        Index("idx_candidate_job_pipeline_invitation_status", "invitation_status"),
        Index("idx_candidate_job_pipeline_next_resume_retry_at", "next_resume_retry_at"),
        Index("idx_candidate_job_pipeline_interview_status", "interview_status"),
        Index("idx_candidate_job_pipeline_composite_status", "composite_assessment_status"),
        Index("idx_candidate_job_pipeline_next_step_status", "next_step_status"),
        Index("idx_candidate_job_pipeline_latest_decision_at", "latest_decision_at"),
        Index("idx_candidate_job_pipeline_latest_interview_assessment", "latest_interview_assessment_id"),
        Index("idx_candidate_job_pipeline_latest_composite_assessment", "latest_composite_assessment_id"),
        Index("idx_candidate_job_pipeline_latest_policy_version", "latest_policy_version_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
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
    interview_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_started")
    composite_assessment_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    next_step_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending_decision")
    latest_invitation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    latest_interview_assessment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    latest_composite_assessment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    latest_policy_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    last_invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_interview_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latest_decision_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    remark: Mapped[str | None] = mapped_column(String(500), nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
