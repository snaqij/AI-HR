"""FastAPI auth dependencies for user and workspace context."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from ..db.session import get_db_session
from ..services.auth import get_auth_service
from .config import get_settings
from .exceptions import InvalidStateError, ResourceNotFoundError


@dataclass(slots=True)
class UserContext:
    """Current authenticated user context."""

    user_id: str
    email: str
    display_name: str
    session_id: str


@dataclass(slots=True)
class WorkspaceContext:
    """Current selected workspace context."""

    workspace_id: str
    workspace_code: str
    role: str


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    value = authorization.strip()
    if not value.lower().startswith("bearer "):
        return None
    token = value[7:].strip()
    return token or None


def require_authenticated_user(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_db_session),
) -> UserContext:
    """Resolve authenticated user from access token."""
    settings = get_settings()
    if not settings.auth_enabled:
        context = UserContext(
            user_id="system",
            email="system@local",
            display_name="System",
            session_id="system",
        )
        session.info["user_id"] = context.user_id
        return context

    token = _extract_bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    service = get_auth_service(session)
    try:
        authenticated = service.authenticate_access_token(token)
    except (InvalidStateError, ResourceNotFoundError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token") from None

    context = UserContext(
        user_id=authenticated.user.id,
        email=authenticated.user.email,
        display_name=authenticated.user.display_name,
        session_id=authenticated.session.id,
    )
    session.info["user_id"] = context.user_id
    return context


def require_workspace_context(
    user: UserContext = Depends(require_authenticated_user),
    x_workspace_id: str | None = Header(default=None),
    session: Session = Depends(get_db_session),
) -> WorkspaceContext:
    """Resolve workspace scope for the request and attach to DB session info."""
    settings = get_settings()
    if not settings.auth_enabled:
        context = WorkspaceContext(workspace_id="default", workspace_code="default", role="workspace_owner")
        session.info["workspace_id"] = context.workspace_id
        return context

    service = get_auth_service(session)
    requested_workspace_id = (x_workspace_id or "").strip()
    if requested_workspace_id:
        try:
            workspace = service.ensure_workspace_access(user_id=user.user_id, workspace_id=requested_workspace_id)
        except ResourceNotFoundError:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace access denied") from None
    else:
        items = service.list_user_workspaces(user.user_id)
        if not items:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No active workspace found")
        workspace = items[0]

    context = WorkspaceContext(
        workspace_id=workspace.id,
        workspace_code=workspace.workspace_code,
        role=workspace.role,
    )
    session.info["workspace_id"] = context.workspace_id
    return context

