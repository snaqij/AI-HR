"""面试持久化模型。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin


class Interview(TimestampMixin, Base):
    """候选人面试安排记录。"""

    __tablename__ = "interviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    candidate_id: Mapped[str] = mapped_column(String(36), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(64), nullable=False, default="boss")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meeting_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_interview_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    target_headcount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    candidate = relationship("Candidate", back_populates="interviews")
    job = relationship("Job", back_populates="interviews")
