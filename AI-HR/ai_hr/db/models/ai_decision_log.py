"""AI 决策审计日志模型。"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class AIDecisionLog(TimestampMixin, Base):
    """记录 AI 决策结果与策略动作。"""

    __tablename__ = "ai_decision_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    module_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    policy_flags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    input_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    extra_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

