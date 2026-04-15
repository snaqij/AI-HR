"""AI 简历相关 API 数据模型。"""

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


class ResumeAttachmentPayload(BaseModel):
    """候选人附件简历元数据。"""

    candidate_id: str
    source_channel: str
    external_candidate_id: str
    file_name: str
    content_type: str | None = None
    source_url: str | None = None
    file_size_bytes: int
    file_sha256: str
    object_storage_provider: str | None = None
    object_storage_bucket: str | None = None
    object_storage_key: str | None = None
    object_storage_url: str | None = None
    last_synced_at: datetime
    created_at: datetime
    updated_at: datetime


class ResumeAttachmentSyncRequest(BaseModel):
    """从 BOSS 同步单个候选人的附件简历。"""

    candidate_id: str = Field(min_length=1)


class ResumeAttachmentSyncResult(BaseModel):
    """单个候选人附件简历同步结果。"""

    attachment: ResumeAttachmentPayload
    candidate_resume_text_updated: bool = False


class ResumeAccessSyncRequest(BaseModel):
    """请求候选人附件简历，并在可用时立即拉取。"""

    candidate_id: str = Field(min_length=1)
    sync_attachment_when_ready: bool = True


class ResumeAccessSyncResult(BaseModel):
    """单个候选人的附件简历申请与同步结果。"""

    candidate_id: str
    external_candidate_id: str
    request_status: int | None = None
    request_sent: bool = False
    resume_visible: bool = False
    attachment_synced: bool = False
    candidate_resume_text_updated: bool = False
    attachment: ResumeAttachmentPayload | None = None
    raw_payload: dict = Field(default_factory=dict)


class ResumeAttachmentBatchSyncRequest(BaseModel):
    """按岗位批量同步候选人附件简历。"""

    candidate_ids: list[str] | None = None
    limit: int | None = Field(default=None, ge=1, le=500)
    stop_on_error: bool = False


class ResumeAttachmentBatchItemResult(BaseModel):
    """单个候选人的批量同步结果。"""

    candidate_id: str
    external_candidate_id: str
    status: str
    attachment: ResumeAttachmentPayload | None = None
    candidate_resume_text_updated: bool = False
    error_message: str | None = None


class ResumeAttachmentBatchSyncResult(BaseModel):
    """岗位维度的附件简历批量同步结果。"""

    job_id: str
    total_candidates: int
    succeeded_count: int
    failed_count: int
    results: list[ResumeAttachmentBatchItemResult]


class ResumeAccessBatchSyncRequest(BaseModel):
    """按岗位批量申请候选人附件简历，并在可用时同步下载。"""

    candidate_ids: list[str] | None = None
    limit: int | None = Field(default=None, ge=1, le=500)
    stop_on_error: bool = False
    sync_attachment_when_ready: bool = True


class ResumeAccessBatchItemResult(BaseModel):
    """单个候选人的附件简历申请结果。"""

    candidate_id: str
    external_candidate_id: str
    status: str
    request_status: int | None = None
    request_sent: bool = False
    resume_visible: bool = False
    attachment_synced: bool = False
    candidate_resume_text_updated: bool = False
    attachment: ResumeAttachmentPayload | None = None
    raw_payload: dict = Field(default_factory=dict)
    error_message: str | None = None


class ResumeAccessBatchSyncResult(BaseModel):
    """岗位维度的附件简历申请与同步结果。"""

    job_id: str
    total_candidates: int
    succeeded_count: int
    failed_count: int
    results: list[ResumeAccessBatchItemResult]
