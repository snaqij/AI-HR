"""AI 面试会话持久化模型。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class AIInterviewSession(TimestampMixin, Base):
    """记录 AI 面试会话生命周期与 RTC 连接信息。"""

    __tablename__ = "ai_interview_sessions"
    __table_args__ = (
        Index("ix_ai_interview_sessions_workspace_id", "workspace_id"),
        Index("ix_ai_interview_sessions_job_created", "job_id", "created_at"),
        Index("ix_ai_interview_sessions_candidate_created", "candidate_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    candidate_id: Mapped[str] = mapped_column(String(36), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="created")
    channel: Mapped[str] = mapped_column(String(64), nullable=False, default="self_hosted_rtc")
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="zh-CN")
    rtc_room_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    # RTC tokens can be much longer than 128 chars.
    join_token: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
