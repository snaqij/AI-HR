"""候选人持久化模型。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin


class Candidate(TimestampMixin, Base):
    """候选人主档模型。"""

    __tablename__ = "candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_channel: Mapped[str] = mapped_column(String(64), nullable=False)
    external_candidate_id: Mapped[str] = mapped_column(Text, nullable=False)
    phone_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resume_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    resume_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_stage: Mapped[str] = mapped_column(String(32), nullable=False, default="new")
    
    # Metadata fields
    school: Mapped[str | None] = mapped_column(String(255), nullable=True)
    degree: Mapped[str | None] = mapped_column(String(64), nullable=True)
    work_experience: Mapped[str | None] = mapped_column(String(128), nullable=True)
    expected_salary: Mapped[str | None] = mapped_column(String(128), nullable=True)
    latest_company: Mapped[str | None] = mapped_column(String(255), nullable=True)

    raw_profile: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    score_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_dimensions: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    score_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation",
        back_populates="candidate",
        cascade="all, delete-orphan",
    )
    interviews: Mapped[list["Interview"]] = relationship(
        "Interview",
        back_populates="candidate",
        cascade="all, delete-orphan",
    )
    identities: Mapped[list["CandidateIdentity"]] = relationship(
        "CandidateIdentity",
        back_populates="candidate",
        cascade="all, delete-orphan",
    )
    resume_profile: Mapped["CandidateResumeProfile | None"] = relationship(
        "CandidateResumeProfile",
        back_populates="candidate",
        cascade="all, delete-orphan",
        uselist=False,
    )
    resume_attachments: Mapped[list["CandidateResumeAttachment"]] = relationship(
        "CandidateResumeAttachment",
        back_populates="candidate",
        cascade="all, delete-orphan",
    )
    resume_access_retries: Mapped[list["CandidateResumeAccessRetry"]] = relationship(
        "CandidateResumeAccessRetry",
        back_populates="candidate",
        cascade="all, delete-orphan",
    )
    resume_risks: Mapped[list["CandidateResumeRisk"]] = relationship(
        "CandidateResumeRisk",
        back_populates="candidate",
        cascade="all, delete-orphan",
    )
    candidate_job_scores: Mapped[list["CandidateJobScore"]] = relationship(
        "CandidateJobScore",
        back_populates="candidate",
        cascade="all, delete-orphan",
    )
    job_candidates: Mapped[list["JobCandidate"]] = relationship(
        "JobCandidate",
        back_populates="candidate",
        cascade="all, delete-orphan",
    )
    shortlists: Mapped[list["JobShortlist"]] = relationship(
        "JobShortlist",
        back_populates="candidate",
        cascade="all, delete-orphan",
    )
