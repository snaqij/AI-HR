"""Auth routes for registration, login, refresh, and user context."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from ...core.auth_dependencies import UserContext, WorkspaceContext, require_authenticated_user, require_workspace_context
from ...core.config import get_settings
from ...core.exceptions import InvalidStateError, ResourceNotFoundError
from ...core.responses import Envelope
from ...db.session import get_db_session
from ...schemas.auth import (
    AuthSessionPayload,
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    MeResponse,
    RefreshResponse,
    RegisterRequest,
    RegisterResponse,
    SendRegisterEmailCodeRequest,
    SendRegisterEmailCodeResponse,
)
from ...services.auth import get_auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _cookie_expire_dt(ttl_seconds: int) -> datetime:
    return datetime.now(UTC) + timedelta(seconds=max(60, int(ttl_seconds)))


def _write_refresh_cookie(response: Response, refresh_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.auth_refresh_cookie_name,
        value=refresh_token,
        httponly=True,
        secure=bool(settings.auth_refresh_cookie_secure),
        samesite=str(settings.auth_refresh_cookie_samesite).lower(),
        path="/",
        expires=_cookie_expire_dt(settings.auth_refresh_token_ttl_seconds),
    )


def _clear_refresh_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=settings.auth_refresh_cookie_name,
        path="/",
    )


@router.post("/register", response_model=Envelope[RegisterResponse], status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_db_session),
) -> Envelope[RegisterResponse]:
    """Register a new account and create a default owner workspace."""
    service = get_auth_service(session)
    try:
        user, workspace, issued = service.register_user(
            email=payload.email,
            verification_code=payload.verification_code,
            password=payload.password,
            display_name=payload.display_name,
            workspace_name=payload.workspace_name,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except InvalidStateError as exc:
        return Envelope.failure("register_failed", str(exc))

    _write_refresh_cookie(response, issued.refresh_token)
    return Envelope.success(
        RegisterResponse(
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            workspace=issued.workspaces[0],
            session=AuthSessionPayload(
                access_token=issued.access_token,
                expires_in=issued.expires_in,
                workspace_id=workspace.id,
                workspaces=issued.workspaces,
            ),
        )
    )


@router.post("/register/email-code", response_model=Envelope[SendRegisterEmailCodeResponse])
def send_register_email_code(
    payload: SendRegisterEmailCodeRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[SendRegisterEmailCodeResponse]:
    """Send a verification code to the registration email."""
    service = get_auth_service(session)
    try:
        result = service.send_register_email_code(email=payload.email)
    except InvalidStateError as exc:
        return Envelope.failure("send_email_code_failed", str(exc))
    return Envelope.success(result)


@router.post("/login", response_model=Envelope[LoginResponse])
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_db_session),
) -> Envelope[LoginResponse]:
    """Authenticate user and issue new access/refresh tokens."""
    service = get_auth_service(session)
    try:
        user, issued = service.login(
            payload=payload,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except (InvalidStateError, ResourceNotFoundError) as exc:
        return Envelope.failure("login_failed", str(exc))

    _write_refresh_cookie(response, issued.refresh_token)
    return Envelope.success(
        LoginResponse(
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            session=AuthSessionPayload(
                access_token=issued.access_token,
                expires_in=issued.expires_in,
                workspace_id=issued.workspace_id,
                workspaces=issued.workspaces,
            ),
        )
    )


@router.post("/refresh", response_model=Envelope[RefreshResponse])
def refresh(
    request: Request,
    response: Response,
    session: Session = Depends(get_db_session),
) -> Envelope[RefreshResponse]:
    """Rotate refresh token and issue a fresh access token."""
    settings = get_settings()
    refresh_token = str(request.cookies.get(settings.auth_refresh_cookie_name) or "").strip()
    if not refresh_token:
        return Envelope.failure("refresh_failed", "Missing refresh token cookie")

    service = get_auth_service(session)
    try:
        _, issued = service.refresh(
            refresh_token=refresh_token,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except (InvalidStateError, ResourceNotFoundError) as exc:
        _clear_refresh_cookie(response)
        return Envelope.failure("refresh_failed", str(exc))

    _write_refresh_cookie(response, issued.refresh_token)
    return Envelope.success(
        RefreshResponse(
            session=AuthSessionPayload(
                access_token=issued.access_token,
                expires_in=issued.expires_in,
                workspace_id=issued.workspace_id,
                workspaces=issued.workspaces,
            )
        )
    )


@router.post("/logout", response_model=Envelope[LogoutResponse])
def logout(
    request: Request,
    response: Response,
    user: UserContext = Depends(require_authenticated_user),
    session: Session = Depends(get_db_session),
) -> Envelope[LogoutResponse]:
    """Revoke current session and clear refresh cookie."""
    del user
    settings = get_settings()
    auth_header = request.headers.get("authorization")
    access_token = auth_header[7:].strip() if auth_header and auth_header.lower().startswith("bearer ") else None
    refresh_token = str(request.cookies.get(settings.auth_refresh_cookie_name) or "").strip() or None
    service = get_auth_service(session)
    service.logout(access_token=access_token, refresh_token=refresh_token)
    _clear_refresh_cookie(response)
    return Envelope.success(LogoutResponse())


@router.get("/me", response_model=Envelope[MeResponse])
def me(
    user: UserContext = Depends(require_authenticated_user),
    workspace: WorkspaceContext = Depends(require_workspace_context),
    session: Session = Depends(get_db_session),
) -> Envelope[MeResponse]:
    """Return current user profile and workspace memberships."""
    service = get_auth_service(session)
    workspaces = service.list_user_workspaces(user.user_id)
    return Envelope.success(
        MeResponse(
            user_id=user.user_id,
            email=user.email,
            display_name=user.display_name,
            status="active",
            current_workspace_id=workspace.workspace_id,
            workspaces=workspaces,
        )
    )
