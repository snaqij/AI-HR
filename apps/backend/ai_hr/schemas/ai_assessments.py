"""Schemas for enterprise interview and composite assessments."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class InterviewAssessmentComputeRequest(BaseModel):
    run_mode: str = Field(default="sync", pattern="^(sync|async)$")
    policy_code: str = Field(default="candidate_progression", min_length=1, max_length=64)
    policy_version: str | None = Field(default=None, max_length=32)
    force_recompute: bool = False


class InterviewAssessmentComputeResponse(BaseModel):
    assessment_id: str
    status: str
    queue_id: str | None = None
    eta_ms: int = 0


class InterviewAssessmentLatestResponse(BaseModel):
    assessment_id: str
    interview_score: float
    dimension_scores: dict[str, float] = Field(default_factory=dict)
    coverage_rate: float
    recommendation: str
    risk_tags: list[str] = Field(default_factory=list)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)


class MarketContext(BaseModel):
    region: str | None = Field(default=None, max_length=64)
    industry: str | None = Field(default=None, max_length=64)
    level: str | None = Field(default=None, max_length=32)
    salary_band: str | None = Field(default=None, max_length=64)


class CompositeAssessmentComputeRequest(BaseModel):
    candidate_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    resume_evaluation_id: str | None = None
    market_context: MarketContext | None = None


class CompositeAssessmentComputeResponse(BaseModel):
    composite_assessment_id: str
    resume_score: float
    interview_score: float
    market_score: float
    composite_score: float
    status: str


class CompositeDecisionRequest(BaseModel):
    policy_code: str = Field(default="candidate_progression", min_length=1, max_length=64)
    policy_version: str | None = Field(default=None, max_length=32)
    dry_run: bool = False


class CompositeDecisionResponse(BaseModel):
    decision: str
    reason_codes: list[str] = Field(default_factory=list)
    composite_confidence: float
    next_step_status: str


class CompositeOverrideRequest(BaseModel):
    operator_id: str = Field(min_length=1, max_length=64)
    decision: str = Field(pattern="^(advance|manual_review|reject)$")
    reason_code: str = Field(min_length=1, max_length=64)
    note: str = Field(min_length=1, max_length=2000)


class CompositeOverrideResponse(BaseModel):
    decision: str
    human_override: bool = True
    override_by: str
    updated_pipeline_status: str


class ReviewQueueTaskItem(BaseModel):
    id: str
    pipeline_id: str
    candidate_id: str
    job_id: str
    priority: int
    status: str
    assignee_id: str | None = None
    queue_type: str
    sla_due_at: datetime | None = None
    age_minutes: int


class ReviewQueueTaskListResponse(BaseModel):
    total: int
    items: list[ReviewQueueTaskItem] = Field(default_factory=list)


class PipelineNextStepPublishRequest(BaseModel):
    assessment_id: str = Field(min_length=1)
    expected_version: str = Field(min_length=1, max_length=32)


class PipelineNextStepPublishResponse(BaseModel):
    next_step_status: str
    published_at: datetime
