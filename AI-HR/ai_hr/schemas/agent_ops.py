"""Schemas for agent operation run/event query APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_key: str | None = None
    agent_code: str
    agent_type: str
    task_type: str
    status: str
    trigger_mode: str
    entity_type: str | None = None
    entity_id: str | None = None
    candidate_id: str | None = None
    job_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    request_payload: dict[str, Any] | None = None
    result_payload: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class AgentRunListResult(BaseModel):
    total: int
    items: list[AgentRunResponse] = Field(default_factory=list)


class AgentEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    sequence_no: int
    agent_code: str
    event_type: str
    event_name: str
    status: str
    message: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    candidate_id: str | None = None
    job_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime
    created_at: datetime
    updated_at: datetime


class AgentEventListResult(BaseModel):
    total: int
    items: list[AgentEventResponse] = Field(default_factory=list)
