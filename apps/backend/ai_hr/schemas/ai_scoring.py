"""AI 批量评分与排序 API 数据模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .candidates import CandidateResponse


class AICandidateBatchScoreRequest(BaseModel):
    """AI 批量评分请求体。"""

    job_id: str = Field(min_length=1)
    candidate_ids: list[str] | None = None


class AICandidateScoreItem(BaseModel):
    """单候选人评分结果。"""

    candidate_id: str
    total_score: float
    dimension_scores: dict[str, float]
    explanation: str
    risk_tags: list[str]
    score_version: str
    scored_at: datetime


class AICandidateBatchScoreResult(BaseModel):
    """AI 批量评分结果。"""

    job_id: str
    scored_count: int
    results: list[AICandidateScoreItem]


class AICandidateRankRequest(BaseModel):
    """AI 候选人排序请求体。"""

    job_id: str = Field(min_length=1)
    top_n: int = Field(default=20, ge=1, le=200)
    min_score: float | None = None


class AIShortlistItem(BaseModel):
    """岗位入围名单条目。"""

    rank: int
    candidate: CandidateResponse
    total_score: float
    dimension_scores: dict[str, float]
    risk_tags: list[str]
    score_version: str
    scored_at: datetime


class AICandidateRankResult(BaseModel):
    """AI 排序结果。"""

    job_id: str
    top_n: int
    shortlist: list[AIShortlistItem]


class JobShortlistResult(BaseModel):
    """岗位入围名单查询结果。"""

    job_id: str
    shortlist: list[AIShortlistItem]

