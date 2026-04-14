"""岗位持久化模型。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin


class Job(TimestampMixin, Base):
    """岗位主档模型。"""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(128), nullable=False)
    salary_range: Mapped[str | None] = mapped_column(String(128), nullable=True)
    requirements: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Automation Settings
    auto_request_resume: Mapped[bool] = mapped_column(default=False)
    min_degree: Mapped[str | None] = mapped_column(String(64), nullable=True)
    min_experience_years: Mapped[int | None] = mapped_column(nullable=True)
    max_daily_resume_requests: Mapped[int] = mapped_column(default=10)

    publications: Mapped[list["JobPublication"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="JobPublication.created_at.desc()",
    )
    interviews: Mapped[list["Interview"]] = relationship(
        "Interview",
        back_populates="job",
        cascade="all, delete-orphan",
    )
    candidate_job_scores: Mapped[list["CandidateJobScore"]] = relationship(
        "CandidateJobScore",
        back_populates="job",
        cascade="all, delete-orphan",
    )
    job_candidates: Mapped[list["JobCandidate"]] = relationship(
        "JobCandidate",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="JobCandidate.last_synced_at.desc()",
    )
    sync_tasks: Mapped[list["JobSyncTask"]] = relationship(
        "JobSyncTask",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="JobSyncTask.created_at.desc()",
    )
    sync_runs: Mapped[list["JobSyncRun"]] = relationship(
        "JobSyncRun",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="JobSyncRun.started_at.desc()",
    )
    shortlists: Mapped[list["JobShortlist"]] = relationship(
        "JobShortlist",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="JobShortlist.rank.asc()",
    )
