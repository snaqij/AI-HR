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
    shortlists: Mapped[list["JobShortlist"]] = relationship(
        "JobShortlist",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="JobShortlist.rank.asc()",
    )
