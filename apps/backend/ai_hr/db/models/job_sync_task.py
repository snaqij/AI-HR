"""岗位候选人同步任务配置。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin

if TYPE_CHECKING:
    from .job import Job
    from .job_sync_run import JobSyncRun


class JobSyncTask(TimestampMixin, Base):
    """持久化定时同步配置。"""

    __tablename__ = "job_sync_tasks"
    __table_args__ = (UniqueConstraint("job_id", "channel", name="uq_job_sync_task_job_channel"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    max_pages: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    reset_cursor_on_next_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_request_resume: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_sync_resume_attachment: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    job: Mapped["Job"] = relationship("Job", back_populates="sync_tasks")
    runs: Mapped[list["JobSyncRun"]] = relationship(
        "JobSyncRun",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="JobSyncRun.started_at.desc()",
    )
