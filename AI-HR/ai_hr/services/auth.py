"""Auth and workspace membership service."""

from __future__ import annotations

import re
import smtplib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.auth_utils import (
    SignedTokenPayload,
    build_signed_token,
    generate_random_token,
    hash_password,
    normalize_email,
    parse_signed_token,
    sha256_hex,
    verify_password,
)
from ..core.config import get_settings
from ..core.exceptions import InvalidStateError, ResourceNotFoundError
from ..db.models import PlatformEmailVerificationCode, PlatformUser, PlatformUserSession, TeamWorkspace, TeamWorkspaceMember
from ..schemas.auth import (
    LoginRequest,
    SendRegisterEmailCodeResponse,
    WorkspaceCreateRequest,
    WorkspaceDetail,
    WorkspaceMemberInviteRequest,
    WorkspaceMemberListResponse,
    WorkspaceMemberSummary,
    WorkspaceMemberUpdateRequest,
    WorkspaceSummary,
    WorkspaceUpdateRequest,
)


@dataclass(slots=True)
class AuthenticatedSession:
    """Validated user session context."""

    user: PlatformUser
    session: PlatformUserSession
    payload: SignedTokenPayload


@dataclass(slots=True)
class SessionIssueResult:
    """Issued token bundle and workspace context."""

    access_token: str
    refresh_token: str
    expires_in: int
    workspace_id: str
    workspaces: list[WorkspaceSummary]


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _utc_timestamp(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    else:
        value = value.astimezone(UTC)
    return int(value.timestamp())


class AuthService:
    """Handles account auth, token lifecycle, and workspace membership checks."""

    def __init__(self, session: Session):
        self._session = session
        self._settings = get_settings()

    def register_user(
        self,
        *,
        email: str,
        verification_code: str,
        password: str,
        display_name: str,
        workspace_name: str,
        ip: str | None,
        user_agent: str | None,
    ) -> tuple[PlatformUser, TeamWorkspace, SessionIssueResult]:
        normalized_email = normalize_email(email)
        self._validate_email(normalized_email)
        self._validate_registration_email_code(email=normalized_email, verification_code=verification_code)
        self._validate_password(password)
        self._validate_display_name(display_name)

        existing = self._session.execute(
            select(PlatformUser).where(PlatformUser.email_normalized == normalized_email)
        ).scalars().first()
        if existing is not None:
            raise InvalidStateError("该邮箱已注册")

        user = PlatformUser(
            email=email.strip(),
            email_normalized=normalized_email,
            display_name=display_name.strip(),
            password_hash=hash_password(password),
            password_algo="pbkdf2_sha256",
            status="active",
            email_verified=True,
            mobile_verified=False,
            password_updated_at=_now(),
            profile_json={},
        )
        self._session.add(user)
        self._session.flush()

        workspace = self._create_workspace_for_user(user_id=user.id, workspace_name=workspace_name)
        self._session.add(
            TeamWorkspaceMember(
                workspace_id=workspace.id,
                user_id=user.id,
                role="workspace_owner",
                status="active",
                invited_by_user_id=user.id,
                joined_at=_now(),
                permissions_json={},
            )
        )
        self._session.flush()

        session_bundle = self._issue_session_tokens(
            user=user,
            workspace_id=workspace.id,
            ip=ip,
            user_agent=user_agent,
            rotate_from=None,
        )
        user.last_login_at = _now()
        user.last_login_ip = ip
        self._session.commit()
        self._session.refresh(user)
        self._session.refresh(workspace)
        return user, workspace, session_bundle

    def send_register_email_code(self, *, email: str) -> SendRegisterEmailCodeResponse:
        normalized_email = normalize_email(email)
        self._validate_email(normalized_email)
        self._ensure_email_not_registered(normalized_email)
        self._enforce_email_code_cooldown(email_normalized=normalized_email, purpose="register")

        now = _now()
        expires_at = now + timedelta(seconds=int(self._settings.auth_email_verification_code_ttl_seconds))
        code = self._generate_email_verification_code()

        active_codes = self._session.execute(
            select(PlatformEmailVerificationCode).where(
                PlatformEmailVerificationCode.email_normalized == normalized_email,
                PlatformEmailVerificationCode.purpose == "register",
                PlatformEmailVerificationCode.status == "active",
            )
        ).scalars().all()
        for entity in active_codes:
            entity.status = "superseded"

        entity = PlatformEmailVerificationCode(
            email=email.strip(),
            email_normalized=normalized_email,
            purpose="register",
            code_hash=sha256_hex(code),
            status="active",
            expires_at=expires_at,
            sent_at=now,
        )
        self._session.add(entity)
        self._session.flush()
        self._send_email_verification_code(email=email.strip(), code=code, purpose="register")
        self._session.commit()

        return SendRegisterEmailCodeResponse(
            email=email.strip(),
            expires_in=int(self._settings.auth_email_verification_code_ttl_seconds),
            resend_cooldown_seconds=int(self._settings.auth_email_verification_resend_cooldown_seconds),
        )

    def login(
        self,
        *,
        payload: LoginRequest,
        ip: str | None,
        user_agent: str | None,
    ) -> tuple[PlatformUser, SessionIssueResult]:
        normalized_email = normalize_email(payload.email)
        self._validate_email(normalized_email)
        user = self._session.execute(
            select(PlatformUser).where(PlatformUser.email_normalized == normalized_email)
        ).scalars().first()
        if user is None:
            raise ResourceNotFoundError("Account not found")
        if user.status != "active":
            raise InvalidStateError("Account is disabled")
        if not verify_password(payload.password, user.password_hash):
            raise InvalidStateError("Invalid credentials")

        workspaces = self.list_user_workspaces(user.id)
        if not workspaces:
            workspace = self._create_workspace_for_user(user_id=user.id, workspace_name="My Team")
            self._session.add(
                TeamWorkspaceMember(
                    workspace_id=workspace.id,
                    user_id=user.id,
                    role="workspace_owner",
                    status="active",
                    invited_by_user_id=user.id,
                    joined_at=_now(),
                    permissions_json={},
                )
            )
            self._session.flush()
            workspaces = self.list_user_workspaces(user.id)
        workspace_id = workspaces[0].id
        session_bundle = self._issue_session_tokens(
            user=user,
            workspace_id=workspace_id,
            ip=ip,
            user_agent=user_agent,
            rotate_from=None,
        )
        user.last_login_at = _now()
        user.last_login_ip = ip
        self._session.commit()
        self._session.refresh(user)
        return user, session_bundle

    def refresh(
        self,
        *,
        refresh_token: str,
        ip: str | None,
        user_agent: str | None,
    ) -> tuple[PlatformUser, SessionIssueResult]:
        authenticated = self._authenticate_token(refresh_token, expected_type="refresh")
        user = authenticated.user
        workspaces = self.list_user_workspaces(user.id)
        if not workspaces:
            raise InvalidStateError("No active workspace found")
        workspace_id = workspaces[0].id
        session_bundle = self._issue_session_tokens(
            user=user,
            workspace_id=workspace_id,
            ip=ip,
            user_agent=user_agent,
            rotate_from=authenticated.session,
        )
        user.last_login_at = _now()
        user.last_login_ip = ip
        self._session.commit()
        self._session.refresh(user)
        return user, session_bundle

    def logout(self, *, access_token: str | None = None, refresh_token: str | None = None) -> bool:
        token = (access_token or refresh_token or "").strip()
        if not token:
            return False
        parsed = parse_signed_token(token)
        if parsed is None:
            return False
        session_entity = self._session.get(PlatformUserSession, parsed.session_id)
        if session_entity is None:
            return False
        session_entity.status = "revoked"
        session_entity.revoked_at = _now()
        self._session.commit()
        return True

    def authenticate_access_token(self, access_token: str) -> AuthenticatedSession:
        return self._authenticate_token(access_token, expected_type="access")

    def list_user_workspaces(self, user_id: str) -> list[WorkspaceSummary]:
        stmt = (
            select(TeamWorkspaceMember, TeamWorkspace)
            .join(TeamWorkspace, TeamWorkspace.id == TeamWorkspaceMember.workspace_id)
            .where(
                TeamWorkspaceMember.user_id == user_id,
                TeamWorkspaceMember.status == "active",
                TeamWorkspace.status == "active",
            )
            .order_by(TeamWorkspaceMember.role.asc(), TeamWorkspace.created_at.asc())
        )
        rows = list(self._session.execute(stmt).all())
        items: list[WorkspaceSummary] = []
        for member, workspace in rows:
            items.append(self._build_workspace_summary(member=member, workspace=workspace))
        return items

    def ensure_workspace_access(self, *, user_id: str, workspace_id: str) -> WorkspaceSummary:
        member, workspace, _ = self._get_workspace_binding(user_id=user_id, workspace_id=workspace_id)
        return self._build_workspace_summary(member=member, workspace=workspace)

    def create_workspace_for_user(self, *, user_id: str, payload: WorkspaceCreateRequest) -> WorkspaceSummary:
        workspace = self._create_workspace_for_user(user_id=user_id, workspace_name=payload.name)
        self._session.add(
            TeamWorkspaceMember(
                workspace_id=workspace.id,
                user_id=user_id,
                role="workspace_owner",
                status="active",
                invited_by_user_id=user_id,
                joined_at=_now(),
                permissions_json={},
            )
        )
        self._session.commit()
        return self._build_workspace_summary(
            member=TeamWorkspaceMember(role="workspace_owner", status="active"),
            workspace=workspace,
        )

    def get_workspace_detail(self, *, user_id: str, workspace_id: str) -> WorkspaceDetail:
        member, workspace, owner = self._get_workspace_binding(user_id=user_id, workspace_id=workspace_id)
        return self._build_workspace_detail(member=member, workspace=workspace, owner=owner)

    def update_workspace(
        self,
        *,
        user_id: str,
        workspace_id: str,
        payload: WorkspaceUpdateRequest,
    ) -> WorkspaceDetail:
        member, workspace, owner = self._get_workspace_binding(user_id=user_id, workspace_id=workspace_id)
        self._ensure_workspace_owner(member)

        normalized_name = str(payload.name or "").strip()
        if not normalized_name:
            raise InvalidStateError("Workspace name is required")

        workspace.name = normalized_name[:128]
        self._session.commit()
        self._session.refresh(workspace)
        return self._build_workspace_detail(member=member, workspace=workspace, owner=owner)

    def list_workspace_members(self, *, user_id: str, workspace_id: str) -> WorkspaceMemberListResponse:
        _, workspace, _ = self._get_workspace_binding(user_id=user_id, workspace_id=workspace_id)
        members = list(
            self._session.execute(
                select(TeamWorkspaceMember).where(
                    TeamWorkspaceMember.workspace_id == workspace.id,
                    TeamWorkspaceMember.status == "active",
                )
            ).scalars().all()
        )

        items: list[WorkspaceMemberSummary] = []
        for member in members:
            user = self._get_platform_user_by_id(member.user_id)
            if user is None:
                continue
            items.append(self._build_workspace_member_summary(member=member, user=user, current_user_id=user_id))
        role_order = {"workspace_owner": 0, "admin": 1, "recruiter": 2, "viewer": 3}
        items.sort(key=lambda item: (role_order.get(item.role, 99), item.display_name.lower(), item.email.lower()))
        return WorkspaceMemberListResponse(workspace_id=workspace.id, total=len(items), items=items)

    def add_workspace_member(
        self,
        *,
        user_id: str,
        workspace_id: str,
        payload: WorkspaceMemberInviteRequest,
    ) -> WorkspaceMemberSummary:
        member, workspace, _ = self._get_workspace_binding(user_id=user_id, workspace_id=workspace_id)
        self._ensure_workspace_owner(member)

        normalized_email = normalize_email(payload.email)
        role = self._normalize_workspace_role(payload.role)

        target_user = self._session.execute(
            select(PlatformUser).where(
                PlatformUser.email_normalized == normalized_email,
                PlatformUser.status == "active",
            )
        ).scalars().first()
        if target_user is None:
            raise InvalidStateError("The invited member must register an account first")

        existing_member = self._session.execute(
            select(TeamWorkspaceMember).where(
                TeamWorkspaceMember.workspace_id == workspace.id,
                TeamWorkspaceMember.user_id == target_user.id,
            )
        ).scalars().first()
        if existing_member is not None:
            if existing_member.status == "active":
                raise InvalidStateError("This user is already a member of the workspace")
            existing_member.status = "active"
            existing_member.role = role
            existing_member.invited_by_user_id = user_id
            existing_member.joined_at = existing_member.joined_at or _now()
            existing_member.permissions_json = existing_member.permissions_json or {}
            target_member = existing_member
        else:
            target_member = TeamWorkspaceMember(
                workspace_id=workspace.id,
                user_id=target_user.id,
                role=role,
                status="active",
                invited_by_user_id=user_id,
                joined_at=_now(),
                permissions_json={},
            )
            self._session.add(target_member)
            self._session.flush()

        self._session.commit()
        self._session.refresh(target_member)
        return self._build_workspace_member_summary(
            member=target_member,
            user=target_user,
            current_user_id=user_id,
        )

    def update_workspace_member(
        self,
        *,
        user_id: str,
        workspace_id: str,
        member_id: str,
        payload: WorkspaceMemberUpdateRequest,
    ) -> WorkspaceMemberSummary:
        requester, workspace, _ = self._get_workspace_binding(user_id=user_id, workspace_id=workspace_id)
        self._ensure_workspace_owner(requester)

        target_member, target_user = self._get_workspace_member_binding(workspace_id=workspace.id, member_id=member_id)
        if target_member.status != "active":
            raise InvalidStateError("Only active members can be updated")
        if target_member.user_id == user_id:
            raise InvalidStateError("You cannot modify your own workspace role")

        next_role = self._normalize_workspace_role(payload.role)
        if target_member.role == "workspace_owner" and next_role != "workspace_owner":
            replacement_owner_id = self._find_replacement_workspace_owner(
                workspace_id=workspace.id,
                excluding_user_id=target_member.user_id,
            )
            if replacement_owner_id is None:
                raise InvalidStateError("At least one workspace owner must remain")
            if workspace.owner_user_id == target_member.user_id:
                workspace.owner_user_id = replacement_owner_id

        target_member.role = next_role
        self._session.commit()
        self._session.refresh(target_member)
        self._session.refresh(workspace)
        return self._build_workspace_member_summary(
            member=target_member,
            user=target_user,
            current_user_id=user_id,
        )

    def remove_workspace_member(self, *, user_id: str, workspace_id: str, member_id: str) -> bool:
        requester, workspace, _ = self._get_workspace_binding(user_id=user_id, workspace_id=workspace_id)
        self._ensure_workspace_owner(requester)

        target_member, _ = self._get_workspace_member_binding(workspace_id=workspace.id, member_id=member_id)
        if target_member.user_id == user_id:
            raise InvalidStateError("You cannot remove yourself from the workspace")
        if target_member.status != "active":
            raise InvalidStateError("This member is already inactive")

        if target_member.role == "workspace_owner":
            replacement_owner_id = self._find_replacement_workspace_owner(
                workspace_id=workspace.id,
                excluding_user_id=target_member.user_id,
            )
            if replacement_owner_id is None:
                raise InvalidStateError("At least one workspace owner must remain")
            if workspace.owner_user_id == target_member.user_id:
                workspace.owner_user_id = replacement_owner_id

        target_member.status = "removed"
        self._session.commit()
        return True

    def _build_workspace_summary(self, *, member: TeamWorkspaceMember, workspace: TeamWorkspace) -> WorkspaceSummary:
        return WorkspaceSummary(
            id=workspace.id,
            workspace_code=workspace.workspace_code,
            name=workspace.name,
            role=member.role,
            status=workspace.status,
        )

    def _build_workspace_detail(
        self,
        *,
        member: TeamWorkspaceMember,
        workspace: TeamWorkspace,
        owner: PlatformUser | None,
    ) -> WorkspaceDetail:
        member_count = len(
            self._session.execute(
                select(TeamWorkspaceMember.id).where(
                    TeamWorkspaceMember.workspace_id == workspace.id,
                    TeamWorkspaceMember.status == "active",
                )
            ).all()
        )
        return WorkspaceDetail(
            id=workspace.id,
            workspace_code=workspace.workspace_code,
            name=workspace.name,
            role=member.role,
            status=workspace.status,
            plan_code=workspace.plan_code,
            owner_user_id=workspace.owner_user_id,
            owner_display_name=owner.display_name if owner is not None else None,
            owner_email=owner.email if owner is not None else None,
            member_count=member_count,
            created_at=workspace.created_at,
            updated_at=workspace.updated_at,
        )

    def _build_workspace_member_summary(
        self,
        *,
        member: TeamWorkspaceMember,
        user: PlatformUser,
        current_user_id: str,
    ) -> WorkspaceMemberSummary:
        display_name = str(user.display_name or "").strip() or user.email
        return WorkspaceMemberSummary(
            id=member.id,
            user_id=user.id,
            display_name=display_name,
            email=user.email,
            avatar_url=user.avatar_url,
            role=member.role,
            status=member.status,
            is_current_user=user.id == current_user_id,
            joined_at=member.joined_at or member.created_at,
            last_active_at=member.last_active_at or user.last_login_at,
        )

    def _get_workspace_binding(
        self,
        *,
        user_id: str,
        workspace_id: str,
    ) -> tuple[TeamWorkspaceMember, TeamWorkspace, PlatformUser | None]:
        row = self._session.execute(
            select(TeamWorkspaceMember, TeamWorkspace)
            .join(TeamWorkspace, TeamWorkspace.id == TeamWorkspaceMember.workspace_id)
            .where(
                TeamWorkspaceMember.user_id == user_id,
                TeamWorkspaceMember.workspace_id == workspace_id,
                TeamWorkspaceMember.status == "active",
                TeamWorkspace.status == "active",
            )
            .limit(1)
        ).first()
        if row is None:
            raise ResourceNotFoundError("Workspace not found or access denied")
        member, workspace = row
        owner = self._get_platform_user_by_id(workspace.owner_user_id)
        return member, workspace, owner

    def _get_workspace_member_binding(self, *, workspace_id: str, member_id: str) -> tuple[TeamWorkspaceMember, PlatformUser]:
        member = self._session.execute(
            select(TeamWorkspaceMember)
            .where(
                TeamWorkspaceMember.workspace_id == workspace_id,
                TeamWorkspaceMember.id == member_id,
            )
            .limit(1)
        ).scalars().first()
        if member is None:
            raise ResourceNotFoundError("Workspace member was not found")
        user = self._get_platform_user_by_id(member.user_id)
        if user is None:
            raise ResourceNotFoundError("Platform user was not found")
        return member, user

    def _get_platform_user_by_id(self, user_id: str | None) -> PlatformUser | None:
        normalized = str(user_id or "").strip()
        if not normalized:
            return None
        return self._session.get(PlatformUser, normalized)

    def _find_replacement_workspace_owner(self, *, workspace_id: str, excluding_user_id: str) -> str | None:
        replacement = self._session.execute(
            select(TeamWorkspaceMember.user_id)
            .where(
                TeamWorkspaceMember.workspace_id == workspace_id,
                TeamWorkspaceMember.user_id != excluding_user_id,
                TeamWorkspaceMember.role == "workspace_owner",
                TeamWorkspaceMember.status == "active",
            )
            .limit(1)
        ).first()
        if replacement is None:
            return None
        return str(replacement[0] or "").strip() or None

    @staticmethod
    def _ensure_workspace_owner(member: TeamWorkspaceMember) -> None:
        if member.role != "workspace_owner":
            raise InvalidStateError("Only workspace owners can manage organization settings")

    @staticmethod
    def _normalize_workspace_role(role: str) -> str:
        normalized = str(role or "").strip().lower()
        if normalized not in {"workspace_owner", "admin", "recruiter", "viewer"}:
            raise InvalidStateError("Unsupported workspace role")
        return normalized

    def _issue_session_tokens(
        self,
        *,
        user: PlatformUser,
        workspace_id: str,
        ip: str | None,
        user_agent: str | None,
        rotate_from: PlatformUserSession | None,
    ) -> SessionIssueResult:
        now = _now()
        access_exp_dt = now + timedelta(seconds=int(self._settings.auth_access_token_ttl_seconds))
        access_exp = _utc_timestamp(access_exp_dt)
        refresh_exp_dt = now + timedelta(seconds=int(self._settings.auth_refresh_token_ttl_seconds))
        refresh_exp = _utc_timestamp(refresh_exp_dt)

        session_entity = rotate_from
        if session_entity is None:
            session_entity = PlatformUserSession(
                user_id=user.id,
                session_token_hash="",
                refresh_token_hash="",
                device_id=None,
                user_agent=user_agent,
                ip=ip,
                status="active",
                expires_at=refresh_exp_dt,
                rotated_at=None,
                revoked_at=None,
            )
            self._session.add(session_entity)
            self._session.flush()
        else:
            if session_entity.status != "active" or session_entity.revoked_at is not None:
                raise InvalidStateError("Session already revoked")
            session_entity.rotated_at = now
            session_entity.user_agent = user_agent
            session_entity.ip = ip
            session_entity.expires_at = refresh_exp_dt

        access_token = build_signed_token(
            token_type="access",
            session_id=session_entity.id,
            user_id=user.id,
            exp=access_exp,
            nonce=generate_random_token(8),
        )
        refresh_token = build_signed_token(
            token_type="refresh",
            session_id=session_entity.id,
            user_id=user.id,
            exp=refresh_exp,
            nonce=generate_random_token(10),
        )

        session_entity.session_token_hash = sha256_hex(access_token)
        session_entity.refresh_token_hash = sha256_hex(refresh_token)
        session_entity.status = "active"
        session_entity.revoked_at = None

        workspaces = self.list_user_workspaces(user.id)
        if not workspaces:
            raise InvalidStateError("No active workspace available")
        if not any(item.id == workspace_id for item in workspaces):
            workspace_id = workspaces[0].id

        return SessionIssueResult(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=int(self._settings.auth_access_token_ttl_seconds),
            workspace_id=workspace_id,
            workspaces=workspaces,
        )

    def _authenticate_token(self, token: str, *, expected_type: str) -> AuthenticatedSession:
        parsed = parse_signed_token(token)
        if parsed is None or parsed.token_type != expected_type:
            raise InvalidStateError("Invalid token")

        session_entity = self._session.get(PlatformUserSession, parsed.session_id)
        if session_entity is None:
            raise ResourceNotFoundError("Session not found")
        if session_entity.status != "active" or session_entity.revoked_at is not None:
            raise InvalidStateError("Session is inactive")
        if expected_type == "refresh" and session_entity.expires_at < _now():
            raise InvalidStateError("Refresh token expired")

        expected_hash = session_entity.refresh_token_hash if expected_type == "refresh" else session_entity.session_token_hash
        if expected_hash != sha256_hex(token):
            raise InvalidStateError("Token has been rotated")

        user = self._session.get(PlatformUser, session_entity.user_id)
        if user is None:
            raise ResourceNotFoundError("User not found")
        if user.status != "active":
            raise InvalidStateError("Account is disabled")
        if parsed.user_id != user.id:
            raise InvalidStateError("Token subject mismatch")
        return AuthenticatedSession(user=user, session=session_entity, payload=parsed)

    def _create_workspace_for_user(self, *, user_id: str, workspace_name: str) -> TeamWorkspace:
        normalized = str(workspace_name or "").strip() or "My Team"
        workspace = TeamWorkspace(
            workspace_code=self._generate_workspace_code(),
            name=normalized[:128],
            owner_user_id=user_id,
            plan_code="pro",
            status="active",
            settings_json={},
        )
        self._session.add(workspace)
        self._session.flush()
        return workspace

    def _generate_workspace_code(self) -> str:
        for _ in range(8):
            code = f"ws_{uuid.uuid4().hex[:10]}"
            exists = self._session.execute(select(TeamWorkspace.id).where(TeamWorkspace.workspace_code == code).limit(1)).first()
            if exists is None:
                return code
        return f"ws_{uuid.uuid4().hex}"

    @staticmethod
    def _validate_password(password: str) -> None:
        if len(str(password or "")) < 8:
            raise InvalidStateError("Password must be at least 8 characters")

    @staticmethod
    def _validate_display_name(display_name: str) -> None:
        if not str(display_name or "").strip():
            raise InvalidStateError("Display name is required")

    @staticmethod
    def _validate_email(email: str) -> None:
        if not email or len(email) > 320:
            raise InvalidStateError("请输入正确的邮箱地址")
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            raise InvalidStateError("请输入正确的邮箱地址")

    def _ensure_email_not_registered(self, email_normalized: str) -> None:
        existing = self._session.execute(
            select(PlatformUser.id).where(PlatformUser.email_normalized == email_normalized).limit(1)
        ).first()
        if existing is not None:
            raise InvalidStateError("该邮箱已注册")

    def _enforce_email_code_cooldown(self, *, email_normalized: str, purpose: str) -> None:
        latest = self._session.execute(
            select(PlatformEmailVerificationCode)
            .where(
                PlatformEmailVerificationCode.email_normalized == email_normalized,
                PlatformEmailVerificationCode.purpose == purpose,
            )
            .order_by(PlatformEmailVerificationCode.created_at.desc())
            .limit(1)
        ).scalars().first()
        if latest is None or latest.sent_at is None:
            return

        cooldown_seconds = int(self._settings.auth_email_verification_resend_cooldown_seconds)
        if cooldown_seconds <= 0:
            return
        if latest.sent_at + timedelta(seconds=cooldown_seconds) > _now():
            raise InvalidStateError("验证码发送过于频繁，请稍后再试")

    def _validate_registration_email_code(self, *, email: str, verification_code: str) -> None:
        normalized_email = normalize_email(email)
        self._ensure_email_not_registered(normalized_email)
        entity = self._session.execute(
            select(PlatformEmailVerificationCode)
            .where(
                PlatformEmailVerificationCode.email_normalized == normalized_email,
                PlatformEmailVerificationCode.purpose == "register",
                PlatformEmailVerificationCode.status == "active",
            )
            .order_by(PlatformEmailVerificationCode.created_at.desc())
            .limit(1)
        ).scalars().first()
        if entity is None:
            raise InvalidStateError("请先获取邮箱验证码")

        now = _now()
        entity.attempt_count = int(entity.attempt_count or 0) + 1
        entity.last_attempt_at = now
        if entity.expires_at <= now:
            entity.status = "expired"
            raise InvalidStateError("验证码错误或已失效")
        if entity.code_hash != sha256_hex(str(verification_code or "").strip()):
            raise InvalidStateError("验证码错误或已失效")

        entity.status = "consumed"
        entity.consumed_at = now

    @staticmethod
    def _generate_email_verification_code() -> str:
        return f"{uuid.uuid4().int % 1000000:06d}"

    def _send_email_verification_code(self, *, email: str, code: str, purpose: str) -> None:
        if not self._settings.email_from_address:
            raise InvalidStateError("SMTP sender address is not configured")
        if not self._settings.email_smtp_host:
            raise InvalidStateError("SMTP host is not configured")

        subject = "AI-HR 注册验证码" if purpose == "register" else "AI-HR 邮箱验证码"
        minutes = max(1, int(self._settings.auth_email_verification_code_ttl_seconds) // 60)

        message = EmailMessage()
        from_name = self._settings.email_from_name.strip()
        message["From"] = f"{from_name} <{self._settings.email_from_address}>"
        message["To"] = email
        message["Subject"] = subject
        message.set_content(
            (
                "您正在注册 AI-HR。\n\n"
                f"本次验证码：{code}\n"
                f"有效期：{minutes} 分钟\n"
                "如非本人操作，请忽略此邮件。"
            )
        )

        if self._settings.email_smtp_use_ssl:
            smtp = smtplib.SMTP_SSL(self._settings.email_smtp_host, self._settings.email_smtp_port, timeout=20)
        else:
            smtp = smtplib.SMTP(self._settings.email_smtp_host, self._settings.email_smtp_port, timeout=20)
        with smtp:
            if self._settings.email_smtp_use_tls and not self._settings.email_smtp_use_ssl:
                smtp.starttls()
            if self._settings.email_smtp_username:
                smtp.login(self._settings.email_smtp_username, self._settings.email_smtp_password or "")
            smtp.send_message(message)


def get_auth_service(session: Session) -> AuthService:
    """Return auth service bound to request-level DB session."""

    return AuthService(session)
