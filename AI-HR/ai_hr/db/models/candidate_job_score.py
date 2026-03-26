"""候选人岗位匹配评分持久化模型。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin


class CandidateJobScore(TimestampMixin, Base):
    """保存候选人在某个岗位下的 AI 评分结果。"""

    __tablename__ = "candidate_job_scores"
    __table_args__ = (UniqueConstraint("candidate_id", "job_id", name="uq_candidate_job_score"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    candidate_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    total_score: Mapped[float] = mapped_column(Float, nullable=False)
    dimension_scores: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    risk_tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    score_version: Mapped[str] = mapped_column(String(64), nullable=False, default="ai-score-v1")
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    candidate = relationship("Candidate", back_populates="candidate_job_scores")
    job = relationship("Job", back_populates="candidate_job_scores")

