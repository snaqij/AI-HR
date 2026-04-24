"""Interview answer-record persistence model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class AIInterviewAnswerRecord(TimestampMixin, Base):
    """Stores answer snapshots mapped to question attempts."""

    __tablename__ = "ai_interview_answer_records"
    __table_args__ = (
        Index("uk_ai_iar_attempt_answer_no", "question_attempt_id", "answer_no", unique=True),
        Index("ix_ai_iar_session_created", "session_id", "created_at"),
        Index("ix_ai_iar_answer_turn_id", "answer_turn_id"),
        Index("ix_ai_iar_attempt_final", "question_attempt_id", "is_final"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    question_attempt_id: Mapped[str] = mapped_column(String(36), nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    answer_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    answer_turn_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="voice")
    asr_confidence: Mapped[float | None] = mapped_column(Numeric(6, 5), nullable=True)
    answer_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    answer_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    answer_ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    ingest_trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
