"""Platform user persistence model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class PlatformUser(TimestampMixin, Base):
    """Stores account-level identity for admin users."""

    __tablename__ = "platform_users"
    __table_args__ = (
        Index("uk_platform_users_email_normalized", "email_normalized", unique=True),
        Index("idx_platform_users_status", "status"),
        Index("idx_platform_users_last_login_at", "last_login_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    email_normalized: Mapped[str] = mapped_column(String(320), nullable=False)
    mobile_e164: Mapped[str | None] = mapped_column(String(32), nullable=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    password_algo: Mapped[str] = mapped_column(String(32), nullable=False, default="pbkdf2_sha256")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    email_verified: Mapped[bool] = mapped_column(nullable=False, default=False)
    mobile_verified: Mapped[bool] = mapped_column(nullable=False, default=False)
    password_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    profile_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

