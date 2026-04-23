"""Schemas for user auth and workspace context APIs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    """Register a new user and bootstrap a default workspace."""

    email: str = Field(min_length=5, max_length=320)
    verification_code: str = Field(min_length=4, max_length=16)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=128)
    workspace_name: str = Field(default="My Team", min_length=1, max_length=128)


class SendRegisterEmailCodeRequest(BaseModel):
    """Request payload for sending a registration verification code."""

    email: str = Field(min_length=5, max_length=320)


class SendRegisterEmailCodeResponse(BaseModel):
    """Response returned after a registration verification code is sent."""

    email: str
    expires_in: int
    resend_cooldown_seconds: int
    sent: bool = True


class LoginRequest(BaseModel):
    """User login request."""

    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=8, max_length=128)


class WorkspaceSummary(BaseModel):
    """Workspace summary visible to a signed-in user."""

    id: str
    workspace_code: str
    name: str
    role: str
    status: str


class AuthSessionPayload(BaseModel):
    """Issued access token payload."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    workspace_id: str
    workspaces: list[WorkspaceSummary]


class RegisterResponse(BaseModel):
    """Response returned after successful registration."""

    user_id: str
    email: str
    display_name: str
    workspace: WorkspaceSummary
    session: AuthSessionPayload


class LoginResponse(BaseModel):
    """Response returned after successful login."""

    user_id: str
    email: str
    display_name: str
    session: AuthSessionPayload


class RefreshResponse(BaseModel):
    """Response returned when refresh token rotates session."""

    session: AuthSessionPayload


class LogoutResponse(BaseModel):
    """Response returned after logout."""

    logged_out: bool = True


class MeResponse(BaseModel):
    """Current identity and workspace context."""

    user_id: str
    email: str
    display_name: str
    status: str
    current_workspace_id: str
    workspaces: list[WorkspaceSummary]


class WorkspaceCreateRequest(BaseModel):
    """Create an additional workspace."""

    name: str = Field(min_length=1, max_length=128)


class WorkspaceCreateResponse(BaseModel):
    """Workspace creation response."""

    workspace: WorkspaceSummary
    created_at: datetime
