"""Candidate composite-assessment persistence model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class CandidateCompositeAssessment(TimestampMixin, Base):
    """Stores cross-signal composite scoring for pipeline decisions."""

    __tablename__ = "candidate_composite_assessments"
    __table_args__ = (
        Index("uk_cca_pipeline_version", "pipeline_id", "composite_version", unique=True),
        Index("idx_cca_candidate_job_score", "candidate_id", "job_id", "final_score"),
        Index("idx_cca_recommendation", "recommendation"),
        Index("idx_cca_status", "status"),
        Index("idx_cca_scored_at", "scored_at"),
        Index("idx_cca_policy_version_id", "policy_version_id"),
        Index("idx_cca_interview_assessment_id", "interview_assessment_id"),
        Index("idx_cca_evaluation_id", "evaluation_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pipeline_id: Mapped[str] = mapped_column(String(36), nullable=False)
    candidate_id: Mapped[str] = mapped_column(String(36), nullable=False)
    job_id: Mapped[str] = mapped_column(String(36), nullable=False)
    evaluation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    interview_assessment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    market_snapshot_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    policy_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    composite_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="completed")
    resume_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    interview_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    market_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    stability_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    risk_penalty_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    final_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    confidence_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    recommendation: Mapped[str] = mapped_column(String(32), nullable=False, default="review")
    hard_reject: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    must_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    factor_breakdown_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    risk_flags_json: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    reason_codes_json: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
