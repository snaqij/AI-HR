"""Agent execution run persistence model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from sqlalchemy import JSON, BigInteger, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from ..base import Base, TimestampMixin


class AgentRun(TimestampMixin, Base):
    """Stores one schedulable agent execution unit and final outcome."""

    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("idx_agent_runs_agent_code", "agent_code"),
        Index("idx_agent_runs_status", "status"),
        Index("idx_agent_runs_task_type", "task_type"),
        Index("idx_agent_runs_candidate_id", "candidate_id"),
        Index("idx_agent_runs_job_id", "job_id"),
        Index("idx_agent_runs_entity", "entity_type", "entity_id"),
        Index("idx_agent_runs_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_code: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_type: Mapped[str] = mapped_column(String(32), nullable=False, default="worker")
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    trigger_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="scheduler")
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    candidate_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    result_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
