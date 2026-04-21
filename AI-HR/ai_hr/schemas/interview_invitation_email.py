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


class InterviewInvitationHistoryItem(BaseModel):
    """Global invitation history item with candidate/job display fields."""

    id: str
    candidate_id: str
    candidate_name: str
    candidate_email: str | None = None
    job_id: str
    job_title: str
    delivery_status: str
    scene: str
    sent_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class InterviewInvitationHistoryResult(BaseModel):
    """Global invitation history list."""

    total: int
    items: list[InterviewInvitationHistoryItem]


class InterviewQuestionAnswerItem(BaseModel):
    """Interview question and candidate answer pair."""

    question_id: str
    question: str
    candidate_answer: str | None = None
    answer_turn_no: int | None = None


class InterviewAIAnalysis(BaseModel):
    """AI interview analysis summary."""

    summary: str | None = None
    recommendation: str | None = None
    dimension_scores: dict[str, Any] = Field(default_factory=dict)
    risk_tags: list[str] = Field(default_factory=list)


class InterviewInvitationRecordDetailResult(BaseModel):
    """Interview record detail for one invitation delivery."""

    delivery_id: str
    candidate_id: str
    candidate_name: str
    candidate_email: str | None = None
    job_id: str
    job_title: str
    delivery_status: str
    invitation_id: str | None = None
    session_id: str | None = None
    has_record: bool = False
    record_message: str | None = None
    questions: list[InterviewQuestionAnswerItem] = Field(default_factory=list)
    analysis: InterviewAIAnalysis = Field(default_factory=InterviewAIAnalysis)
