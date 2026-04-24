"""岗位候选人同步执行流水。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin

if TYPE_CHECKING:
    from .job import Job
    from .job_sync_task import JobSyncTask


class JobSyncRun(TimestampMixin, Base):
    """记录每一次手动或定时同步执行结果。"""

    __tablename__ = "job_sync_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("job_sync_tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    channel: Mapped[str | None] = mapped_column(String(64), nullable=True)
    max_pages: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reset_cursor: Mapped[bool] = mapped_column(nullable=False, default=False)
    total_pulled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    task: Mapped["JobSyncTask | None"] = relationship("JobSyncTask", back_populates="runs")
    job: Mapped["Job"] = relationship("Job", back_populates="sync_runs")
