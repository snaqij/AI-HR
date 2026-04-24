"""AI 会话意图分类与回复生成模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AIIntentClassifyRequest(BaseModel):
    """意图分类请求体。"""

    conversation_id: str = Field(min_length=1)
    message: str = Field(min_length=1)


class AIIntentClassifyResult(BaseModel):
    """意图分类结果。"""

    conversation_id: str
    intent: str
    confidence: float
    policy_flags: list[str] = Field(default_factory=list)
    explanation: str
    provider: str
    model_name: str
    prompt_version: str


class AIReplyGenerateRequest(BaseModel):
    """自动回复生成请求体。"""

    conversation_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    intent_hint: str | None = None


class AIReplyGenerateResult(BaseModel):
    """自动回复生成结果。"""

    conversation_id: str
    intent: str
    reply_text: str
    confidence: float
    action: str
    decision_reason: str
    policy_flags: list[str] = Field(default_factory=list)
    explanation: str
    provider: str
    model_name: str
    prompt_version: str


class AIReplyAlertStatsResult(BaseModel):
    """自动回复告警统计结果。"""

    window_minutes: int
    total: int
    handoff_count: int
    blocked_count: int
    handoff_rate: float
    blocked_rate: float
    min_samples: int
    alerting: bool
    alert_reasons: list[str] = Field(default_factory=list)
