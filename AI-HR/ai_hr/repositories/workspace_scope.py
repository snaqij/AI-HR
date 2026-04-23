"""Workspace scoping helpers for repository queries."""

from __future__ import annotations

from sqlalchemy.orm import Session


def get_workspace_id(session: Session) -> str | None:
    """Get current workspace scope from request-bound SQLAlchemy session."""
    value = session.info.get("workspace_id")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def get_user_id(session: Session) -> str | None:
    """Get current authenticated user id from request-bound SQLAlchemy session."""
    value = session.info.get("user_id")
    if value is None:
        return None
    text = str(value).strip()
    return text or None
