"""Candidate evaluation API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .candidates import CandidateResponse, CandidateSummaryResponse


class CandidateEvaluationRequest(BaseModel):
    """Request body for evaluating a candidate against a job."""

    evaluation_version: str = Field(default="v1", min_length=1, max_length=32)
    force_refresh: bool = False


class CandidateEvaluationResponse(BaseModel):
    """Detailed evaluation response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    candidate_id: str
    job_id: str
    resume_attachment_id: str | None
    evaluation_version: str
    source: str
    status: str
    match_score: float
    competitiveness_score: float
    final_score: float
    confidence_score: float | None
    recommendation: str
    summary: str | None
    dimension_scores: dict[str, float]
    strengths: list[str]
    weaknesses: list[str]
    highlights: list[str]
    risk_flags: list[str]
    job_requirement_coverage: dict[str, str]
    raw_llm_output: dict[str, Any] | None
    invited_flag: bool
    reviewed_by: str | None
    reviewed_at: datetime | None
    evaluated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CandidateEvaluationDetailResult(BaseModel):
    """Single candidate evaluation result with candidate snapshot."""

    candidate: CandidateResponse
    evaluation: CandidateEvaluationResponse
    pipeline_status: dict[str, Any]


class CandidateEvaluationListItem(BaseModel):
    """Item returned in job-level evaluation listings."""

    candidate: CandidateSummaryResponse
    evaluation: CandidateEvaluationResponse


class CandidateEvaluationListResult(BaseModel):
    """Job-level evaluation list result."""

    job_id: str
    total: int
    items: list[CandidateEvaluationListItem]


class CandidateEvaluationUpdateRequest(BaseModel):
    """Manual update payload for a candidate evaluation."""

    recommendation: str | None = None
    summary: str | None = None
    strengths: list[str] | None = None
    weaknesses: list[str] | None = None
    highlights: list[str] | None = None
    risk_flags: list[str] | None = None
    reviewed_by: str | None = None
