"""AI 离线评测运行记录模型。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class AIEvalRun(TimestampMixin, Base):
    """记录一次离线评测任务的输入参数与指标结果。"""

    __tablename__ = "ai_eval_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    eval_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    dataset_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="completed")
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
