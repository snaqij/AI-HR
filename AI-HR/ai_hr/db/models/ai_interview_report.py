"""AI 面试报告持久化模型。"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class AIInterviewReport(TimestampMixin, Base):
    """记录会话级评估报告、维度分与结论。"""

    __tablename__ = "ai_interview_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("ai_interview_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    report_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    dimension_scores_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    risk_tags_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    recommendation: Mapped[str] = mapped_column(String(32), nullable=False, default="manual_review")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

