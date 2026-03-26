"""AI 面试人工接管持久化模型。"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class AIInterviewHandoff(TimestampMixin, Base):
    """记录面试中转人工的触发原因与操作者。"""

    __tablename__ = "ai_interview_handoffs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("ai_interview_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(128), nullable=False)
    trigger_flags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    operator: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

