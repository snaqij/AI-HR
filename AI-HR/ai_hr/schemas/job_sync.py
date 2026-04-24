"""Job sync task and run schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class JobSyncTaskUpsertRequest(BaseModel):
    """Create or update a scheduled sync task."""

    channel: str = Field(default="boss", min_length=1, max_length=64)
    enabled: bool = True
    interval_minutes: int = Field(default=30, ge=1, le=1440)
    max_pages: int = Field(default=2, ge=1, le=20)
    reset_cursor_on_next_run: bool = False
    auto_request_resume: bool = False
    auto_sync_resume_attachment: bool = False
    run_immediately: bool = False


class JobSyncTaskResponse(BaseModel):
    """Scheduled sync task response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    channel: str
    enabled: bool
    interval_minutes: int
    max_pages: int
    reset_cursor_on_next_run: bool
    auto_request_resume: bool
    auto_sync_resume_attachment: bool
    next_run_at: datetime | None
    last_run_at: datetime | None
    last_status: str | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class JobSyncRunResponse(BaseModel):
    """Sync run record response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str | None
    job_id: str
    trigger_type: str
    status: str
    channel: str | None
    max_pages: int
    reset_cursor: bool
    total_pulled: int
    total_created: int
    total_updated: int
    started_at: datetime
    finished_at: datetime | None
    error_message: str | None
    summary_payload: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class JobSyncTaskExecuteResult(BaseModel):
    """Result of manually triggering a scheduled sync task."""

    task: JobSyncTaskResponse
    run: JobSyncRunResponse
    summary: dict = Field(default_factory=dict)


class JobSyncTaskListResult(BaseModel):
    """List of sync tasks for a job."""

    job_id: str
    tasks: list[JobSyncTaskResponse]


class JobSyncRunListResult(BaseModel):
    """List of sync run records for a job."""

    job_id: str
    runs: list[JobSyncRunResponse]
