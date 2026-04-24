"""AI 功能灰度开关模型。"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class AIFeatureFlag(TimestampMixin, Base):
    """按功能和租户控制 AI 灰度策略。"""

    __tablename__ = "ai_feature_flags"
    __table_args__ = (UniqueConstraint("feature_key", "tenant_id", "job_id", name="uq_ai_feature_tenant_job"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    feature_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    job_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None, index=True)
    rollout_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fallback_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="rule_only")
