"""Review-queue task persistence model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class ReviewQueueTask(TimestampMixin, Base):
    """Queues human-review tasks for borderline or risky cases."""

    __tablename__ = "review_queue_tasks"
    __table_args__ = (
        Index("idx_rqt_status_priority", "status", "priority", "sla_due_at"),
        Index("idx_rqt_pipeline_status", "pipeline_id", "status"),
        Index("idx_rqt_assignee_status", "assignee_id", "status"),
        Index("idx_rqt_queue_type_status", "queue_type", "status"),
        Index("idx_rqt_composite_assessment_id", "composite_assessment_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pipeline_id: Mapped[str] = mapped_column(String(36), nullable=False)
    composite_assessment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    queue_type: Mapped[str] = mapped_column(String(32), nullable=False, default="human_review")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assignee_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    checklist_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
