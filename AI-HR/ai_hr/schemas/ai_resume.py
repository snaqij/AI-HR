"""AI 简历解析相关 API 数据模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ResumeRiskItem(BaseModel):
    """简历风险项。"""

    risk_code: str
    risk_level: str
    detail: str


class ResumeProfilePayload(BaseModel):
    """简历画像数据载荷。"""

    candidate_id: str
    raw_text: str
    parse_status: str
    parser_version: str
    confidence: float
    parsed_profile: dict
    normalized_profile: dict
    risks: list[ResumeRiskItem]
    created_at: datetime
    updated_at: datetime


class ResumeParseRequest(BaseModel):
    """简历解析请求体。"""

    candidate_id: str = Field(min_length=1)
    resume_text: str | None = None


class ResumeParseResult(BaseModel):
    """简历解析结果。"""

    profile: ResumeProfilePayload


class ResumeNormalizeRequest(BaseModel):
    """简历标准化请求体。"""

    candidate_id: str = Field(min_length=1)


class ResumeNormalizeResult(BaseModel):
    """简历标准化结果。"""

    profile: ResumeProfilePayload


class CandidateResumeProfileResult(BaseModel):
    """候选人简历结构化画像查询结果。"""

    profile: ResumeProfilePayload

