"""AI 离线评测接口数据模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AIEvalRunRequest(BaseModel):
    """发起离线评测请求。"""

    eval_type: str = Field(min_length=1, max_length=64)
    dataset_version: str = Field(min_length=1, max_length=64)
    model_version: str = Field(min_length=1, max_length=128)


class AIEvalRunResult(BaseModel):
    """离线评测运行结果。"""

    run_id: str
    eval_type: str
    dataset_version: str
    model_version: str
    status: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime
    finished_at: datetime


class AIEvalReportResult(BaseModel):
    """离线评测报告结果。"""

    run_id: str
    eval_type: str
    dataset_version: str
    model_version: str
    status: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    finished_at: datetime
