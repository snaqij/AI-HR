"""AI Prompt 版本模型。"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, Boolean, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class AIPromptVersion(TimestampMixin, Base):
    """定义任务级 Prompt 模板版本。"""

    __tablename__ = "ai_prompt_versions"
    __table_args__ = (UniqueConstraint("task_key", "version", name="uq_ai_prompt_task_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    user_template: Mapped[str] = mapped_column(Text, nullable=False)
    output_schema: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)

