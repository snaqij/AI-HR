"""岗位入围名单持久化模型。"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin


class JobShortlist(TimestampMixin, Base):
    """保存岗位候选人排序后的入围名单。"""

    __tablename__ = "job_shortlists"
    __table_args__ = (UniqueConstraint("job_id", "candidate_id", name="uq_job_shortlist_candidate"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    candidate_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")

    job = relationship("Job", back_populates="shortlists")
    candidate = relationship("Candidate", back_populates="shortlists")

