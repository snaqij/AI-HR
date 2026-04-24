"""Team workspace persistence model."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class TeamWorkspace(TimestampMixin, Base):
    """Stores enterprise workspace metadata."""

    __tablename__ = "team_workspaces"
    __table_args__ = (
        Index("uk_team_workspaces_workspace_code", "workspace_code", unique=True),
        Index("idx_team_workspaces_owner_user", "owner_user_id"),
        Index("idx_team_workspaces_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    owner_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    plan_code: Mapped[str] = mapped_column(String(32), nullable=False, default="pro")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    settings_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

