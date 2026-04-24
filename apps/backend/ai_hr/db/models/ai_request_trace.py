"""AI 调用链路追踪模型。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class AIRequestTrace(TimestampMixin, Base):
    """记录一次 LLM 请求调用的运行细节。"""

    __tablename__ = "ai_request_traces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    task_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[str] = mapped_column(String(32), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fallback_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

