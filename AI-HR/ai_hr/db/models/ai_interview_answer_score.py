"""Interview answer-score persistence model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class AIInterviewAnswerScore(TimestampMixin, Base):
    """Stores per-answer scoring outcomes."""

    __tablename__ = "ai_interview_answer_scores"
    __table_args__ = (
        Index("uk_ai_ias_answer_version", "answer_record_id", "score_version", unique=True),
        Index("ix_ai_ias_attempt_status", "question_attempt_id", "status"),
        Index("ix_ai_ias_overall_score", "overall_score"),
        Index("ix_ai_ias_scored_at", "scored_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    answer_record_id: Mapped[str] = mapped_column(String(36), nullable=False)
    question_attempt_id: Mapped[str] = mapped_column(String(36), nullable=False)
    score_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    scoring_model: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="final")
    overall_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    content_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    reasoning_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    communication_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    relevance_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    confidence_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    risk_penalty_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    strengths_json: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    gaps_json: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    risk_flags_json: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    evidence_json: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
