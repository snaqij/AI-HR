"""审批、审计与漏斗指标相关 Schema。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ApprovalCreateRequest(BaseModel):
    """审批创建请求。"""

    action_type: str = Field(min_length=1, max_length=64, examples=["interview_batch_send"])
    entity_type: str = Field(min_length=1, max_length=64, examples=["job"])
    entity_id: str = Field(min_length=1, max_length=36)
    requested_by: str = Field(default="system", min_length=1, max_length=64)
    reason: str | None = Field(default=None, max_length=2000)
    payload: dict[str, Any] = Field(default_factory=dict)


class ApprovalDecisionRequest(BaseModel):
    """审批决策请求。"""

    decision: str = Field(pattern="^(approved|rejected)$")
    decided_by: str = Field(default="system", min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=2000)


class ApprovalResponse(BaseModel):
    """审批响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    action_type: str
    entity_type: str
    entity_id: str
    requested_by: str
    status: str
    reason: str | None
    payload: dict[str, Any]
    decided_by: str | None
    decided_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AuditEventItem(BaseModel):
    """审计事件项。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    event_type: str
    entity_type: str
    entity_id: str
    channel: str | None
    operator: str | None
    session_id: str | None
    job_id: str | None
    status: str
    occurred_at: datetime
    payload: dict[str, Any]


class AuditEventQueryResult(BaseModel):
    """审计查询结果。"""

    total: int
    items: list[AuditEventItem] = Field(default_factory=list)


class FunnelStageItem(BaseModel):
    """漏斗阶段项。"""

    stage: str
    count: int
    conversion_rate: float | None = None


class FunnelMetricsResult(BaseModel):
    """漏斗聚合结果。"""

    stages: list[FunnelStageItem] = Field(default_factory=list)
