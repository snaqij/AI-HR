"""Channel credential persistence model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class ChannelCredential(TimestampMixin, Base):
    """Stores encrypted credentials for third-party platforms (e.g., BOSS cookies)."""

    __tablename__ = "channel_credentials"
    __table_args__ = (
        Index("idx_channel_credentials_channel_provider", "channel", "provider"),
        Index("idx_channel_credentials_is_active", "is_active"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    channel: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g., 'boss'
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    account_name: Mapped[str] = mapped_column(String(128), nullable=False)  # e.g., 'Primary Account'
    
    # Encrypted JSON string containing the sensitive data (cookies, tokens, etc.)
    encrypted_config: Mapped[str] = mapped_column(Text, nullable=False)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="normal", nullable=False) # normal, expired, banned
    
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
