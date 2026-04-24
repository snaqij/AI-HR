"""候选人简历结构化画像持久化模型。"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin


class CandidateResumeProfile(TimestampMixin, Base):
    """保存候选人简历解析与标准化结果。"""

    __tablename__ = "candidate_resume_profiles"
    __table_args__ = (UniqueConstraint("candidate_id", name="uq_resume_profile_candidate_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    candidate_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    parsed_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    normalized_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    parse_status: Mapped[str] = mapped_column(String(32), nullable=False, default="parsed")
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False, default="heuristic-v1")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    candidate = relationship("Candidate", back_populates="resume_profile")

