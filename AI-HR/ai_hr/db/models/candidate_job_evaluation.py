"""Candidate-job evaluation persistence model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class CandidateJobEvaluation(TimestampMixin, Base):
    """Stores detailed evaluation results for a candidate under a job."""

    __tablename__ = "candidate_job_evaluations"
    __table_args__ = (
        Index("uk_candidate_job_eval_unique", "candidate_id", "job_id", "evaluation_version", unique=True),
        Index("idx_candidate_job_eval_candidate", "candidate_id"),
        Index("idx_candidate_job_eval_job", "job_id"),
        Index("idx_candidate_job_eval_status", "status"),
        Index("idx_candidate_job_eval_recommendation", "recommendation"),
        Index("idx_candidate_job_eval_final_score", "final_score"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    candidate_id: Mapped[str] = mapped_column(String(36), nullable=False)
    job_id: Mapped[str] = mapped_column(String(36), nullable=False)
    resume_attachment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    evaluation_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="hybrid")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    match_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    competitiveness_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    final_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    confidence_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    recommendation: Mapped[str] = mapped_column(String(32), nullable=False, default="review")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    dimension_scores: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    strengths: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    weaknesses: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    highlights: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    risk_flags: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    job_requirement_coverage: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    raw_llm_output: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    invited_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
