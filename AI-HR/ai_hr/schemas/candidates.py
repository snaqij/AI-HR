"""候选人 API 数据模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CandidateImportItem(BaseModel):
    """候选人导入条目。"""

    name: str = Field(min_length=1, max_length=255)
    source_channel: str = Field(min_length=1, max_length=64)
    external_candidate_id: str = Field(min_length=1, max_length=512)
    phone_hash: str | None = None
    email_hash: str | None = None
    email: str | None = None
    resume_url: str | None = None
    resume_text: str | None = None
    school: str | None = None
    degree: str | None = None
    work_experience: str | None = None
    expected_salary: str | None = None
    latest_company: str | None = None
    applied_at: str | datetime | None = None
    raw_profile: dict = Field(default_factory=dict)


class CandidateImportRequest(BaseModel):
    """候选人导入请求体。"""

    candidates: list[CandidateImportItem] = Field(min_length=1)


class CandidateResponse(BaseModel):
    """候选人标准响应体。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    source_channel: str
    external_candidate_id: str
    phone_hash: str | None
    email_hash: str | None
    email: str | None
    resume_url: str | None
    resume_text: str | None
    current_stage: str
    school: str | None
    degree: str | None
    work_experience: str | None
    expected_salary: str | None
    latest_company: str | None
    raw_profile: dict
    score_total: float | None
    score_dimensions: dict
    score_explanation: str | None
    scored_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CandidateSummaryResponse(BaseModel):
    """Lightweight candidate response for list pages."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    email: str | None
    current_stage: str
    school: str | None
    degree: str | None
    work_experience: str | None
    expected_salary: str | None
    latest_company: str | None
    created_at: datetime
    updated_at: datetime


class CandidateImportResult(BaseModel):
    """候选人导入结果。"""

    created_count: int
    updated_count: int
    candidates: list[CandidateResponse]


class CandidateScoreRequest(BaseModel):
    """候选人评分请求体。"""

    job_id: str | None = None


class CandidateScoreResult(BaseModel):
    """候选人评分结果。"""

    candidate: CandidateResponse
    total_score: float
    dimensions: dict[str, float]
    explanation: str
