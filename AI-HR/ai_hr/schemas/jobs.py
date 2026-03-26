"""岗位 API 数据模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class JobCreateRequest(BaseModel):
    """岗位创建请求体。"""

    title: str = Field(min_length=1, max_length=255)
    department: str | None = Field(default=None, max_length=255)
    city: str = Field(min_length=1, max_length=128)
    salary_range: str | None = Field(default=None, max_length=128)
    requirements: str = Field(min_length=1)


class JobPublicationResponse(BaseModel):
    """岗位发布记录响应体。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    channel: str
    status: str
    external_job_id: str | None
    error_message: str | None
    request_payload: dict
    response_payload: dict
    published_at: datetime | None
    last_synced_at: datetime | None
    applicant_sync_cursor: str | None
    created_at: datetime
    updated_at: datetime


class JobResponse(BaseModel):
    """岗位标准响应体。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    department: str | None
    city: str
    salary_range: str | None
    requirements: str
    status: str
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None = None
    publications: list[JobPublicationResponse] = Field(default_factory=list)


class JobPublishRequest(BaseModel):
    """岗位发布请求体。"""

    channels: list[str] = Field(min_length=1, default_factory=lambda: ["boss"])


class JobPublishResult(BaseModel):
    """岗位发布结果。"""

    job: JobResponse
    publications: list[JobPublicationResponse]


class JobPublishStatusResponse(BaseModel):
    """岗位发布状态结果。"""

    job_id: str
    publications: list[JobPublicationResponse]


class JobCandidateSyncRequest(BaseModel):
    """岗位候选人同步请求体。"""

    channels: list[str] | None = None
    max_pages: int = Field(default=1, ge=1, le=20)


class JobCandidateSyncChannelResult(BaseModel):
    """单渠道候选人同步结果。"""

    channel: str
    external_job_id: str
    pulled_count: int
    created_count: int
    updated_count: int
    next_cursor: str | None
    has_more: bool


class JobCandidateSyncResult(BaseModel):
    """岗位候选人同步汇总结果。"""

    job_id: str
    total_pulled: int
    total_created: int
    total_updated: int
    channels: list[JobCandidateSyncChannelResult]
