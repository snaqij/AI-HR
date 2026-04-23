"""Interview question-attempt persistence model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class AIInterviewQuestionAttempt(TimestampMixin, Base):
    """Tracks question-level lifecycle during an interview session."""

    __tablename__ = "ai_interview_question_attempts"
    __table_args__ = (
        Index("uk_ai_iqa_session_seq", "session_id", "question_seq", unique=True),
        Index("ix_ai_iqa_session_status", "session_id", "status"),
        Index("ix_ai_iqa_question_id", "question_id"),
        Index("ix_ai_iqa_asked_turn_id", "asked_turn_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    question_set_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    question_id: Mapped[str] = mapped_column(String(128), nullable=False)
    question_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    question_type: Mapped[str] = mapped_column(String(32), nullable=False, default="mixed")
    competency_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    difficulty_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    asked_turn_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    asked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="asked")
    timeout_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    context_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
