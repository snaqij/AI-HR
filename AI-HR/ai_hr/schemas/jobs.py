"""岗位 API 数据模型。"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from .candidates import CandidateSummaryResponse
from .candidate_evaluations import CandidateEvaluationResponse
from .interview_invitation_email import CandidateEmailDeliveryResponse
from .ai_resume import ResumeAccessBatchSyncResult


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
    
    # Automation Settings
    auto_request_resume: bool = False
    min_degree: str | None = None
    min_experience_years: int | None = None
    max_daily_resume_requests: int = 10

    candidate_count: int = 0
    publications: list[JobPublicationResponse] = Field(default_factory=list)


class JobUpdateSettingsRequest(BaseModel):
    """岗位自动化配置更新请求。"""

    auto_request_resume: bool | None = None
    min_degree: str | None = None
    min_experience_years: int | None = None
    max_daily_resume_requests: int | None = None


class JobListResult(BaseModel):
    """岗位列表结果。"""

    total: int
    items: list[JobResponse]


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
    reset_cursor: bool = False
    auto_request_resume: bool = False
    auto_sync_resume_attachment: bool = False


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
    resume_access: "ResumeAccessBatchSyncResult | None" = None


class JobResumeReadySyncRequest(BaseModel):
    """岗位已获简历候选人同步请求体。"""

    channel: str = Field(default="boss", min_length=1, max_length=64)
    label_id: int = Field(default=4, ge=1)
    sort: str = ""


class JobResumeReadySyncResult(BaseModel):
    """岗位已获简历候选人同步结果。"""

    job_id: str
    channel: str
    label_id: int
    pulled_count: int
    created_count: int
    updated_count: int


class RemoteJobSyncItem(BaseModel):
    """远端岗位标准化数据。"""

    external_job_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=255)
    status: str = Field(default="published", max_length=32)
    city: str = Field(default="Unknown", max_length=128)
    salary: str | None = Field(default=None, max_length=128)
    department: str | None = Field(default=None, max_length=255)
    requirements: str | None = None
    raw_payload: dict = Field(default_factory=dict)


class RemoteJobListItem(BaseModel):
    """远端岗位展示项。"""

    external_job_id: str
    title: str
    status: str | None
    city: str | None
    salary: str | None = None
    raw_payload: dict = Field(default_factory=dict)


class RemoteJobListResult(BaseModel):
    """远端岗位列表结果。"""

    channel: str
    page: int
    page_size: int
    jobs: list[RemoteJobListItem]


class RemoteJobImportRequest(BaseModel):
    """将渠道侧岗位导入本地。"""

    channel: str = Field(default="boss", min_length=1, max_length=64)
    page: int = Field(default=1, ge=1, le=200)
    page_size: int = Field(default=20, ge=1, le=100)


class RemoteJobImportResult(BaseModel):
    """远端岗位导入结果。"""

    channel: str
    created_count: int
    updated_count: int
    jobs: list[JobResponse]


class JobCandidateItem(BaseModel):
    """岗位下的候选人展示项。"""

    candidate: "CandidateSummaryResponse"
    channel: str
    external_candidate_id: str
    external_job_id: str | None
    stage: str
    source_status: str | None
    applied_at: datetime | None = None
    first_synced_at: datetime
    last_synced_at: datetime
    source_payload: dict = Field(default_factory=dict)
    
    # Pipeline status fields (from CandidateJobPipeline)
    resume_request_status: str | None = None
    resume_download_status: str | None = None
    last_resume_requested_at: datetime | None = None

    # Embedded related data for performance
    evaluation: "CandidateEvaluationResponse | None" = None
    latest_delivery: "CandidateEmailDeliveryResponse | None" = None


class JobCandidateListResult(BaseModel):
    """岗位候选人列表。"""

    job_id: str
    total: int
    evaluated_count: int = 0
    sent_count: int = 0
    limit: int
    next_cursor: str | None = None
    has_more: bool = False
    candidates: list[JobCandidateItem]


class JobCandidateStageUpdateRequest(BaseModel):
    """更新岗位下候选人的流程阶段。"""

    stage: str = Field(min_length=1, max_length=64)


JobCandidateItem.model_rebuild()
JobCandidateSyncResult.model_rebuild()
