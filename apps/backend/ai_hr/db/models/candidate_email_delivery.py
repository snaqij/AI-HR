"""Candidate email delivery persistence model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class CandidateEmailDelivery(TimestampMixin, Base):
    """Stores rendered email payloads and delivery audit information."""

    __tablename__ = "candidate_email_deliveries"
    __table_args__ = (
        Index("idx_candidate_email_delivery_workspace", "workspace_id"),
        Index("idx_candidate_email_delivery_created_by", "created_by_user_id"),
        Index("idx_candidate_email_delivery_candidate", "candidate_id"),
        Index("idx_candidate_email_delivery_job", "job_id"),
        Index("idx_candidate_email_delivery_status", "status"),
        Index("idx_candidate_email_delivery_scene", "scene"),
        Index("idx_candidate_email_delivery_sent_at", "sent_at"),
        Index("idx_candidate_email_delivery_provider_message_id", "provider_message_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    candidate_id: Mapped[str] = mapped_column(String(36), nullable=False)
    job_id: Mapped[str] = mapped_column(String(36), nullable=False)
    evaluation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    invitation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    template_code: Mapped[str] = mapped_column(String(64), nullable=False)
    scene: Mapped[str] = mapped_column(String(64), nullable=False, default="interview_invitation")
    to_email: Mapped[str] = mapped_column(String(255), nullable=False)
    cc_emails: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    bcc_emails: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    html_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    clicked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
