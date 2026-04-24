"""AI 模型运行时配置模型。"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class AIModelConfig(TimestampMixin, Base):
    """定义某类 AI 任务的模型路由参数。"""

    __tablename__ = "ai_model_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="mock")
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    temperature_milli: Mapped[int] = mapped_column(Integer, nullable=False, default=200)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

