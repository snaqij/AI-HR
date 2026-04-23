"""Interview assessment persistence model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class AIInterviewAssessment(TimestampMixin, Base):
    """Stores session-level interview scoring and recommendation."""

    __tablename__ = "ai_interview_assessments"
    __table_args__ = (
        Index("uk_ai_ia_session_version", "session_id", "assessment_version", unique=True),
        Index("ix_ai_ia_session_status", "session_id", "status"),
        Index("ix_ai_ia_recommendation", "recommendation"),
        Index("ix_ai_ia_total_score", "total_score"),
        Index("ix_ai_ia_evaluated_at", "evaluated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    assessment_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="computed")
    evaluated_by: Mapped[str] = mapped_column(String(32), nullable=False, default="ai")
    scoring_formula_version: Mapped[str] = mapped_column(String(32), nullable=False, default="interview_v1")
    coverage_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    competency_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    communication_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    consistency_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    stability_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    risk_penalty_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    total_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    confidence_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    recommendation: Mapped[str] = mapped_column(String(32), nullable=False, default="review")
    hard_fail: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    must_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    strengths_json: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    gaps_json: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    risk_flags_json: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    evidence_json: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    dimension_weights_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
