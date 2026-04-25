"""LLM 输出契约定义。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ResumeParseLLMOutput(BaseModel):
    """简历解析输出契约。"""

    skills: list[str] = Field(default_factory=list)
    experience_years: float | None = None
    education_level: str | None = None
    projects: list[dict] = Field(default_factory=list)
    confidence: float = 0.0
    risk_tags: list[str] = Field(default_factory=list)


class CandidateScoreLLMOutput(BaseModel):
    """候选人评分输出契约。"""

    dimension_scores: dict[str, float] = Field(default_factory=dict)
    total_score: float = 0.0
    explanation: str = ""
    risk_tags: list[str] = Field(default_factory=list)


class CandidateEvaluationLLMOutput(BaseModel):
    """Detailed candidate evaluation output contract."""

    match_score: float = 0.0
    competitiveness_score: float = 0.0
    final_score: float = 0.0
    confidence_score: float = 0.0
    dimension_scores: dict[str, float] = Field(default_factory=dict)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    recommendation: str = "review"
    summary: str = ""
    job_requirement_coverage: dict[str, str] = Field(default_factory=dict)


class AnswerEvaluationLLMOutput(BaseModel):
    """单题答案评估输出契约。"""

    completeness: float = 0.0
    logic: float = 0.0
    evidence: float = 0.0
    communication: float = 0.0
    domain_fit: float = 0.0
    confidence: float = 0.0
    risk_tags: list[str] = Field(default_factory=list)


class IntentClassifyLLMOutput(BaseModel):
    """意图分类输出契约。"""

    intent: str
    confidence: float
    policy_flags: list[str] = Field(default_factory=list)


class ReplyGenerateLLMOutput(BaseModel):
    """回复生成输出契约。"""

    reply_text: str
    confidence: float
    policy_flags: list[str] = Field(default_factory=list)


class InterviewQuestionItemLLMOutput(BaseModel):
    question: str
    dimension: str
    expected_signal: str
    followup_condition: str


class InterviewQuestionSetLLMOutput(BaseModel):
    questions: list[InterviewQuestionItemLLMOutput] = Field(default_factory=list)
    confidence: float = 0.0
    policy_flags: list[str] = Field(default_factory=list)


class InterviewFollowupLLMOutput(BaseModel):
    followup_question: str = ""
    reason: str = ""
    policy_flags: list[str] = Field(default_factory=list)
    confidence: float = 0.0
