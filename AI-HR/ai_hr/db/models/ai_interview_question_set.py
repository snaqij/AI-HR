"""AI 面试问题集持久化模型。"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class AIInterviewQuestionSet(TimestampMixin, Base):
    """记录面试前生成的问题树与版本。"""

    __tablename__ = "ai_interview_question_sets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("ai_interview_sessions.id", ondelete="CASCADE"), nullable=True, index=True)
    invitation_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("ai_interview_invitations.id", ondelete="CASCADE"), nullable=True, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="resume+jd")
    questions_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)

