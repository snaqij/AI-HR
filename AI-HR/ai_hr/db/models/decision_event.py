"""Decision-event persistence model."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class DecisionEvent(TimestampMixin, Base):
    """Stores decision and override audit events."""

    __tablename__ = "decision_events"
    __table_args__ = (
        Index("idx_de_pipeline_created", "pipeline_id", "created_at"),
        Index("idx_de_decision", "decision"),
        Index("idx_de_event_type", "event_type"),
        Index("idx_de_trace_id", "trace_id"),
        Index("idx_de_composite_assessment_id", "composite_assessment_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pipeline_id: Mapped[str] = mapped_column(String(36), nullable=False)
    composite_assessment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    policy_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, default="auto_decision")
    from_step: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_step: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False, default="system")
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
