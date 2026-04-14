"""Schemas for interview invitation email management."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class InterviewInvitationEmailSendRequest(BaseModel):
    """Manual invitation send request."""

    evaluation_id: str | None = None
    template_code: str | None = None
    note: str | None = None


class InterviewInvitationEmailSendResult(BaseModel):
    """Manual invitation send result."""

    candidate_id: str
    job_id: str
    evaluation_id: str
    delivery_id: str
    invitation_id: str
    to_email: str
    status: str
    invitation_link: str


class CandidateEmailDeliveryResponse(BaseModel):
    """Email delivery audit response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    candidate_id: str
    job_id: str
    evaluation_id: str | None
    invitation_id: str | None
    template_code: str
    scene: str
    to_email: str
    subject: str
    provider: str | None
    provider_message_id: str | None
    status: str
    retry_count: int
    max_retry_count: int
    last_error: str | None
    sent_at: datetime | None
    delivered_at: datetime | None
    opened_at: datetime | None
    clicked_at: datetime | None
    payload: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class CandidateEmailDeliveryListResult(BaseModel):
    """Email delivery list result for a job."""

    job_id: str
    total: int
    items: list[CandidateEmailDeliveryResponse]
