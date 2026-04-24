"""AI 面试邀请持久化模型。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class AIInterviewInvitation(TimestampMixin, Base):
    """记录 AI 面试邀请链接及其状态。"""

    __tablename__ = "ai_interview_invitations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    candidate_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    job_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")  # pending, ready, expired
    invitation_channel: Mapped[str] = mapped_column(String(32), nullable=False, default="email")
    email_delivery_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_use_count: Mapped[int] = mapped_column(Integer, nullable=False, default=10)

    # Optional metadata captured during generation
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
