"""岗位与候选人关联模型。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, UniqueConstraint, and_
from sqlalchemy.orm import Mapped, mapped_column, relationship, foreign

from ..base import Base, TimestampMixin


class JobCandidate(TimestampMixin, Base):
    """记录候选人被哪个岗位同步进来，以及最后一次同步状态。"""

    __tablename__ = "job_candidates"
    __table_args__ = (
        UniqueConstraint("job_id", "channel", "external_candidate_id", name="uq_job_candidate_source_external"),
        Index("idx_job_candidate_filter", "job_id", "stage", "last_synced_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    publication_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("job_publications.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    candidate_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel: Mapped[str] = mapped_column(String(64), nullable=False)
    external_job_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    external_candidate_id: Mapped[str] = mapped_column(String(512), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="new")
    source_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    job: Mapped["Job"] = relationship("Job", back_populates="job_candidates")
    publication: Mapped["JobPublication | None"] = relationship("JobPublication", back_populates="job_candidates")
    candidate: Mapped["Candidate"] = relationship("Candidate", back_populates="job_candidates")

    pipeline: Mapped["CandidateJobPipeline | None"] = relationship(
        "CandidateJobPipeline",
        primaryjoin="and_(JobCandidate.candidate_id == foreign(CandidateJobPipeline.candidate_id), JobCandidate.job_id == foreign(CandidateJobPipeline.job_id))",
        viewonly=True,
        uselist=False,
    )

    # Performance optimization: virtual relationship for fast list-page access to evaluation and latest delivery status
    evaluation: Mapped["CandidateJobEvaluation | None"] = relationship(
        "CandidateJobEvaluation",
        primaryjoin="and_(JobCandidate.candidate_id == foreign(CandidateJobEvaluation.candidate_id), JobCandidate.job_id == foreign(CandidateJobEvaluation.job_id))",
        order_by="desc(CandidateJobEvaluation.created_at)",
        viewonly=True,
        uselist=False,
    )

    latest_delivery: Mapped["CandidateEmailDelivery | None"] = relationship(
        "CandidateEmailDelivery",
        primaryjoin="and_(JobCandidate.candidate_id == foreign(CandidateEmailDelivery.candidate_id), JobCandidate.job_id == foreign(CandidateEmailDelivery.job_id))",
        order_by="desc(CandidateEmailDelivery.created_at)",
        viewonly=True,
        uselist=False,
    )
