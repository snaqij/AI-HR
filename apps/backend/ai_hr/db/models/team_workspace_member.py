"""Team workspace member persistence model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class TeamWorkspaceMember(TimestampMixin, Base):
    """Stores user-workspace role bindings."""

    __tablename__ = "team_workspace_members"
    __table_args__ = (
        Index("uk_team_workspace_members_workspace_user", "workspace_id", "user_id", unique=True),
        Index("idx_team_workspace_members_user_status", "user_id", "status"),
        Index("idx_team_workspace_members_workspace_role", "workspace_id", "role"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="recruiter")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    invited_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    permissions_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

