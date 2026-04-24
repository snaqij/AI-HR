"""Workspace routes for listing and creating team spaces."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core.auth_dependencies import UserContext, WorkspaceContext, require_authenticated_user, require_workspace_context
from ...core.responses import Envelope
from ...db.session import get_db_session
from ...schemas.auth import (
    WorkspaceCreateRequest,
    WorkspaceCreateResponse,
    WorkspaceDetail,
    WorkspaceMemberInviteRequest,
    WorkspaceMemberListResponse,
    WorkspaceMemberRemoveResponse,
    WorkspaceMemberSummary,
    WorkspaceMemberUpdateRequest,
    WorkspaceSummary,
    WorkspaceUpdateRequest,
)
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


@router.get("/{workspace_id}", response_model=Envelope[WorkspaceDetail])
def get_workspace_detail(
    workspace_id: str,
    user: UserContext = Depends(require_authenticated_user),
    session: Session = Depends(get_db_session),
) -> Envelope[WorkspaceDetail]:
    """Return detailed workspace profile for settings pages."""
    service = get_auth_service(session)
    return Envelope.success(service.get_workspace_detail(user_id=user.user_id, workspace_id=workspace_id))


@router.patch("/{workspace_id}", response_model=Envelope[WorkspaceDetail])
def update_workspace(
    workspace_id: str,
    payload: WorkspaceUpdateRequest,
    user: UserContext = Depends(require_authenticated_user),
    session: Session = Depends(get_db_session),
) -> Envelope[WorkspaceDetail]:
    """Update editable workspace profile fields."""
    service = get_auth_service(session)
    return Envelope.success(service.update_workspace(user_id=user.user_id, workspace_id=workspace_id, payload=payload))


@router.get("/{workspace_id}/members", response_model=Envelope[WorkspaceMemberListResponse])
def list_workspace_members(
    workspace_id: str,
    user: UserContext = Depends(require_authenticated_user),
    session: Session = Depends(get_db_session),
) -> Envelope[WorkspaceMemberListResponse]:
    """List active members in the workspace."""
    service = get_auth_service(session)
    return Envelope.success(service.list_workspace_members(user_id=user.user_id, workspace_id=workspace_id))


@router.post("/{workspace_id}/members", response_model=Envelope[WorkspaceMemberSummary])
def add_workspace_member(
    workspace_id: str,
    payload: WorkspaceMemberInviteRequest,
    user: UserContext = Depends(require_authenticated_user),
    session: Session = Depends(get_db_session),
) -> Envelope[WorkspaceMemberSummary]:
    """Add an existing registered platform user into the workspace."""
    service = get_auth_service(session)
    return Envelope.success(service.add_workspace_member(user_id=user.user_id, workspace_id=workspace_id, payload=payload))


@router.patch("/{workspace_id}/members/{member_id}", response_model=Envelope[WorkspaceMemberSummary])
def update_workspace_member(
    workspace_id: str,
    member_id: str,
    payload: WorkspaceMemberUpdateRequest,
    user: UserContext = Depends(require_authenticated_user),
    session: Session = Depends(get_db_session),
) -> Envelope[WorkspaceMemberSummary]:
    """Update a workspace member role."""
    service = get_auth_service(session)
    return Envelope.success(
        service.update_workspace_member(
            user_id=user.user_id,
            workspace_id=workspace_id,
            member_id=member_id,
            payload=payload,
        )
    )


@router.delete("/{workspace_id}/members/{member_id}", response_model=Envelope[WorkspaceMemberRemoveResponse])
def remove_workspace_member(
    workspace_id: str,
    member_id: str,
    user: UserContext = Depends(require_authenticated_user),
    session: Session = Depends(get_db_session),
) -> Envelope[WorkspaceMemberRemoveResponse]:
    """Remove a workspace member from the team."""
    service = get_auth_service(session)
    service.remove_workspace_member(user_id=user.user_id, workspace_id=workspace_id, member_id=member_id)
    return Envelope.success(WorkspaceMemberRemoveResponse(member_id=member_id, removed=True))
