"""Email template persistence model."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, Boolean, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class EmailTemplate(TimestampMixin, Base):
    """Stores email templates used by automated invitation delivery."""

    __tablename__ = "email_templates"
    __table_args__ = (
        Index("uk_email_templates_code", "template_code", unique=True),
        Index("idx_email_templates_scene", "scene"),
        Index("idx_email_templates_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    template_code: Mapped[str] = mapped_column(String(64), nullable=False)
    template_name: Mapped[str] = mapped_column(String(128), nullable=False)
    scene: Mapped[str] = mapped_column(String(64), nullable=False, default="interview_invitation")
    subject_template: Mapped[str] = mapped_column(String(500), nullable=False)
    html_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    variables_schema: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    remark: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
