"""AI 面试问答轮次持久化模型。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class AIInterviewTurn(TimestampMixin, Base):
    """记录面试中的单轮发言、转写与策略信号。"""

    __tablename__ = "ai_interview_turns"
    __table_args__ = (
        Index("ix_ai_interview_turns_session_turn", "session_id", "turn_no"),
        Index("ix_ai_interview_turns_session_created", "session_id", "created_at"),
        Index("ix_ai_interview_turns_question_attempt_id", "question_attempt_id"),
        Index("ix_ai_interview_turns_session_question_seq", "session_id", "question_seq"),
        Index("ix_ai_interview_turns_ingest_trace_id", "ingest_trace_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("ai_interview_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    turn_no: Mapped[int] = mapped_column(Integer, nullable=False)
    question_attempt_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    question_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    question_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    speaker: Mapped[str] = mapped_column(String(32), nullable=False)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    audio_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ingest_trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    policy_flags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
