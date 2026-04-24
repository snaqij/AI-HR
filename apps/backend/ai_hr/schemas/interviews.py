"""面试排期 API 数据模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class InterviewScheduleRequest(BaseModel):
    """创建面试排期请求体。"""

    candidate_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    channel: str = Field(default="boss", min_length=1, max_length=64)
    scheduled_at: datetime
    meeting_link: str | None = None
    meeting_provider: str | None = None
    note: str | None = None
    auto_dispatch: bool = False
    target_headcount: int | None = Field(default=None, ge=1)


class InterviewDispatchRequest(BaseModel):
    """执行约面请求体。"""

    force: bool = False


class InterviewSyncStatusRequest(BaseModel):
    """同步约面状态请求体。"""

    force: bool = False


class InterviewResponse(BaseModel):
    """面试记录标准响应体。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    candidate_id: str
    job_id: str
    channel: str
    status: str
    scheduled_at: datetime | None
    meeting_link: str | None
    external_interview_id: str | None
    target_headcount: int | None
    payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class InterviewScheduleResult(BaseModel):
    """面试排期创建结果。"""

    interview: InterviewResponse
    dispatched: bool
    dispatch_payload: dict[str, Any] = Field(default_factory=dict)


class InterviewDispatchResult(BaseModel):
    """面试执行结果。"""

    interview: InterviewResponse
    status: str
    dispatch_payload: dict[str, Any] = Field(default_factory=dict)


class InterviewSyncStatusResult(BaseModel):
    """面试状态同步结果。"""

    interview: InterviewResponse
    status: str
    sync_payload: dict[str, Any] = Field(default_factory=dict)


class InterviewPlanRequest(BaseModel):
    """按岗位人数生成邀约计划请求体。"""

    headcount: int = Field(ge=1)


class InterviewPlanItem(BaseModel):
    """单个候选人的邀约计划项。"""

    candidate_id: str
    rank: int
    reason: str


class InterviewPlanResult(BaseModel):
    """岗位邀约计划结果。"""

    job_id: str
    headcount: int
    already_planned_or_sent: int
    planned_count: int
    plan: list[InterviewPlanItem] = Field(default_factory=list)


class InterviewSendRequest(BaseModel):
    """按计划批量发送面试邀约请求体。"""

    headcount: int = Field(ge=1)
    channel: str = Field(default="boss", min_length=1, max_length=64)
    scheduled_at: datetime
    meeting_link: str | None = None
    meeting_provider: str | None = None
    note: str | None = None
    auto_dispatch: bool = True


class InterviewSendItemResult(BaseModel):
    """单个候选人发送结果。"""

    candidate_id: str
    status: str
    interview_id: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class InterviewSendResult(BaseModel):
    """批量发送面试邀约结果。"""

    job_id: str
    headcount: int
    attempted: int
    created: int
    skipped: int
    sent: int
    failed: int
    results: list[InterviewSendItemResult] = Field(default_factory=list)


class InterviewProgressResult(BaseModel):
    """岗位面试邀约进度汇总。"""

    job_id: str
    total_target: int
    sent: int
    success: int
    failed: int
    pending_confirmation: int
