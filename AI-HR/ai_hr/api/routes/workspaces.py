"""Workspace routes for listing and creating team spaces."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core.auth_dependencies import UserContext, WorkspaceContext, require_authenticated_user, require_workspace_context
from ...core.responses import Envelope
from ...db.session import get_db_session
from ...schemas.auth import WorkspaceCreateRequest, WorkspaceCreateResponse, WorkspaceSummary
from ...services.auth import get_auth_service

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.get("", response_model=Envelope[list[WorkspaceSummary]])
def list_my_workspaces(
    user: UserContext = Depends(require_authenticated_user),
    session: Session = Depends(get_db_session),
) -> Envelope[list[WorkspaceSummary]]:
    """List all active workspaces current user can access."""
    service = get_auth_service(session)
    return Envelope.success(service.list_user_workspaces(user.user_id))


@router.post("", response_model=Envelope[WorkspaceCreateResponse])
def create_workspace(
    payload: WorkspaceCreateRequest,
    user: UserContext = Depends(require_authenticated_user),
    _: WorkspaceContext = Depends(require_workspace_context),
    session: Session = Depends(get_db_session),
) -> Envelope[WorkspaceCreateResponse]:
    """Create a new workspace and assign current user as owner."""
    service = get_auth_service(session)
    workspace = service.create_workspace_for_user(user_id=user.user_id, payload=payload)
    return Envelope.success(WorkspaceCreateResponse(workspace=workspace, created_at=datetime.now(UTC).replace(tzinfo=None)))
