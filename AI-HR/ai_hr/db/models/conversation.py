"""会话持久化模型。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin


class Conversation(TimestampMixin, Base):
    """候选人与招聘方之间的会话主表。"""

    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("channel", "external_conversation_id", name="uq_conversation_channel_external_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    candidate_id: Mapped[str] = mapped_column(String(36), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(64), nullable=False)
    external_conversation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    context_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    candidate = relationship("Candidate", back_populates="conversations")
