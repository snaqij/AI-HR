"""Agent event stream persistence model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from ..base import Base, TimestampMixin


class AgentEvent(TimestampMixin, Base):
    """Stores stage-level events produced by one agent run."""

    __tablename__ = "agent_events"
    __table_args__ = (
        Index("idx_agent_events_run_id_sequence", "run_id", "sequence_no"),
        Index("idx_agent_events_agent_code", "agent_code"),
        Index("idx_agent_events_status", "status"),
        Index("idx_agent_events_candidate_id", "candidate_id"),
        Index("idx_agent_events_job_id", "job_id"),
        Index("idx_agent_events_occurred_at", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    agent_code: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, default="run")
    event_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="info")
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    candidate_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
