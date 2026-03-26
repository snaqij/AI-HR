"""AI 运行时管理 API 数据模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RuntimeFeatureFlagRequest(BaseModel):
    """运行时功能开关写入请求。"""

    tenant_id: str | None = None
    # 新增 job_id 以支持租户+岗位灰度命中；为空时保持原有行为。
    job_id: str | None = None
    enabled: bool = True
    rollout_percent: int = Field(default=100, ge=0, le=100)
    fallback_mode: str = Field(default="llm_first", min_length=1, max_length=32)


class RuntimeFeatureFlagResponse(BaseModel):
    """运行时功能开关响应。"""

    feature_key: str
    tenant_id: str | None
    job_id: str | None = None
    enabled: bool
    rollout_percent: int
    fallback_mode: str
    created_at: datetime
    updated_at: datetime


class RuntimeFeatureFlagResolveResponse(BaseModel):
    """功能开关命中解析结果。"""

    feature_key: str
    tenant_id: str | None = None
    job_id: str | None = None
    enabled: bool
    matched_scope: str = Field(description="命中范围：tenant_job/tenant/global/default")
    matched_tenant_id: str | None = None
    matched_job_id: str | None = None
    fallback_mode: str | None = None
    rollout_percent: int | None = None


class RuntimeFeatureFlagRollbackRequest(BaseModel):
    """功能开关回滚请求。"""

    tenant_id: str | None = None
    job_id: str | None = None
    reason: str = Field(default="manual_rollback", min_length=1, max_length=256)
    operator: str | None = Field(default=None, max_length=64)
    target_version: str | None = Field(default="rule_only", max_length=64)


class RuntimeFeatureFlagRollbackResponse(RuntimeFeatureFlagResponse):
    """功能开关回滚响应（含元信息）。"""

    rollback_reason: str
    rollback_operator: str | None = None
    rollback_target_version: str | None = None
    rollback_at: datetime


class RuntimeAuditDecisionRecord(BaseModel):
    """运行时审计记录（最小返回字段）。"""

    id: str
    trace_id: str
    module_key: str
    entity_type: str
    entity_id: str
    action: str
    confidence: float | None = None
    policy_flags: list[str] = Field(default_factory=list)
    risk_tags: list[str] = Field(default_factory=list)
    provider: str | None = None
    model_name: str | None = None
    prompt_version: str | None = None
    extra_payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class RuntimeModelConfigRequest(BaseModel):
    """模型配置写入请求。"""

    provider: str = Field(min_length=1, max_length=32)
    model_name: str = Field(min_length=1, max_length=128)
    temperature_milli: int = Field(default=200, ge=0, le=2000)
    timeout_seconds: int = Field(default=8, ge=1, le=120)
    max_retries: int = Field(default=2, ge=0, le=5)
    is_active: bool = True
    weight: int = Field(default=100, ge=1, le=1000)


class RuntimeModelConfigResponse(BaseModel):
    """模型配置响应。"""

    task_key: str
    provider: str
    model_name: str
    temperature_milli: int
    timeout_seconds: int
    max_retries: int
    is_active: bool
    weight: int
    created_at: datetime
    updated_at: datetime


class RuntimePromptRequest(BaseModel):
    """Prompt 版本写入请求。"""

    version: str = Field(min_length=1, max_length=32)
    system_prompt: str = Field(min_length=1)
    user_template: str = Field(min_length=1)
    output_schema: dict = Field(default_factory=dict)
    is_active: bool = True
    created_by: str | None = None


class RuntimePromptResponse(BaseModel):
    """Prompt 版本响应。"""

    task_key: str
    version: str
    system_prompt: str
    user_template: str
    output_schema: dict
    is_active: bool
    created_by: str | None
    created_at: datetime
    updated_at: datetime
