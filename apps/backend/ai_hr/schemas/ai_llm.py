"""LLM 平台通用数据模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LLMInvokeRequest(BaseModel):
    """LLM 调用请求。"""

    task_key: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    timeout_seconds: int = Field(default=8, ge=1, le=120)
    max_retries: int = Field(default=2, ge=0, le=5)
    temperature_milli: int = Field(default=200, ge=0, le=2000)


class LLMInvokeResult(BaseModel):
    """LLM 调用结果。"""

    trace_id: str
    task_key: str
    provider: str
    model_name: str
    prompt_version: str
    content: dict
    latency_ms: int
    retry_count: int
    fallback_used: bool = False

