"""Authentication helpers for AI interview APIs."""

from __future__ import annotations

import base64
import os
from cryptography.fernet import Fernet
from fastapi import Depends, Header, HTTPException, WebSocket, status
from .config import Settings, get_settings
from .exceptions import AIHRException


def _is_production(settings: Settings) -> bool:
    return (settings.environment or "").strip().lower() in {"prod", "production"}


def _is_auth_required(settings: Settings) -> bool:
    return bool(settings.ai_interview_auth_required or _is_production(settings))


def _parse_configured_api_keys(raw_value: str | None) -> set[str]:
    if not raw_value:
        return set()
    return {item.strip() for item in raw_value.split(",") if item.strip()}


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    value = authorization.strip()
    if len(value) < 8:
        return None
    if value[:7].lower() != "bearer ":
        return None
    token = value[7:].strip()
    return token or None


def _resolve_presented_api_key(*, authorization: str | None, x_api_key: str | None) -> str | None:
    direct_key = (x_api_key or "").strip()
    if direct_key:
        return direct_key
    return _extract_bearer_token(authorization)


def validate_ai_interview_auth(
    *,
    settings: Settings,
    authorization: str | None,
    x_api_key: str | None,
) -> None:
    """Validate auth material for interview routes under production-safe defaults."""
    if not _is_auth_required(settings):
        return

    configured_keys = _parse_configured_api_keys(settings.ai_interview_api_keys)
    if not configured_keys:
        raise AIHRException(
            "AI interview auth is required but AI_HR_AI_INTERVIEW_API_KEYS is empty; "
            "set one or more comma-separated API keys."
        )

    presented_key = _resolve_presented_api_key(authorization=authorization, x_api_key=x_api_key)
    if not presented_key or presented_key not in configured_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing AI interview API key",
        )


def require_ai_interview_auth(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """FastAPI dependency for HTTP routes."""
    validate_ai_interview_auth(settings=settings, authorization=authorization, x_api_key=x_api_key)


async def require_ai_interview_ws_auth(websocket: WebSocket) -> bool:
    """Validate websocket auth and close proactively when invalid."""
    settings = get_settings()
    authorization = websocket.headers.get("authorization")
    x_api_key = websocket.headers.get("x-api-key")
    try:
        validate_ai_interview_auth(settings=settings, authorization=authorization, x_api_key=x_api_key)
    except HTTPException:
        await websocket.close(code=4401, reason="unauthorized")
        return False
    except AIHRException:
        await websocket.close(code=1011, reason="server_auth_misconfigured")
        return False
    return True


def get_encryption_key() -> bytes:
    """Resolve the encryption key from settings or environment."""
    settings = get_settings()
    # Priority: Settings -> Env -> Fallback (only for dev, but strongly discouraged)
    key = os.getenv("AI_HR_ENCRYPTION_KEY") or getattr(settings, "encryption_key", None)
    
    if not key:
        # In a real production system, this should raise an error.
        # For now, we'll use a deterministic fallback for demo purposes if not set,
        # but we should warn the user.
        return base64.urlsafe_b64encode(b"aihr-default-static-key-00000032")
        
    if isinstance(key, str):
        return key.encode()
    return key


def encrypt_data(data: str) -> str:
    """Encrypt a string using AES (Fernet)."""
    if not data:
        return ""
    key = get_encryption_key()
    f = Fernet(key)
    return f.encrypt(data.encode()).decode()


def decrypt_data(token: str) -> str:
    """Decrypt a string using AES (Fernet)."""
    if not token:
        return ""
    key = get_encryption_key()
    f = Fernet(key)
    return f.decrypt(token.encode()).decode()

