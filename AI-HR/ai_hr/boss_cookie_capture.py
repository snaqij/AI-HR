"""Helpers for capturing BOSS cookies and syncing them into AI-HR."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import httpx


DEFAULT_BOSS_DOMAIN = "zhipin.com"
DEFAULT_REQUIRED_COOKIE_NAMES = ("bst",)


@dataclass(frozen=True, slots=True)
class AIHRAuthSession:
    """Authentication context used by AI-HR credential APIs."""

    access_token: str | None = None
    workspace_id: str | None = None


def is_boss_cookie_domain(domain: str | None, *, root_domain: str = DEFAULT_BOSS_DOMAIN) -> bool:
    """Return whether a cookie domain belongs to BOSS."""
    normalized_domain = str(domain or "").strip().lower().lstrip(".")
    normalized_root = str(root_domain).strip().lower().lstrip(".")
    if not normalized_domain or not normalized_root:
        return False
    return normalized_domain == normalized_root or normalized_domain.endswith(f".{normalized_root}")


def filter_boss_cookies(
    cookies: Sequence[Mapping[str, Any]],
    *,
    root_domain: str = DEFAULT_BOSS_DOMAIN,
) -> list[dict[str, str]]:
    """Keep non-empty BOSS cookies and deduplicate by name."""
    deduplicated: dict[str, str] = {}
    for cookie in cookies:
        if not is_boss_cookie_domain(cookie.get("domain"), root_domain=root_domain):
            continue
        name = str(cookie.get("name") or "").strip()
        value = str(cookie.get("value") or "").strip()
        if not name or not value:
            continue
        deduplicated[name] = value
    return [{"name": name, "value": deduplicated[name]} for name in sorted(deduplicated)]


def extract_cookie_names(cookies: Sequence[Mapping[str, Any]]) -> list[str]:
    """Return sorted cookie names for user-facing logging."""
    return sorted(
        {
            str(cookie.get("name") or "").strip()
            for cookie in cookies
            if str(cookie.get("name") or "").strip()
        }
    )


def has_required_cookie_names(
    cookies: Sequence[Mapping[str, Any]],
    *,
    required_names: Sequence[str] = DEFAULT_REQUIRED_COOKIE_NAMES,
) -> bool:
    """Return whether all required cookie names are present."""
    cookie_names = set(extract_cookie_names(cookies))
    required = {str(name).strip() for name in required_names if str(name).strip()}
    if not required:
        return bool(cookie_names)
    return required.issubset(cookie_names)


def build_cookie_header(cookies: Sequence[Mapping[str, Any]]) -> str:
    """Render cookies into a raw Cookie header string."""
    pairs = []
    for cookie in cookies:
        name = str(cookie.get("name") or "").strip()
        value = str(cookie.get("value") or "").strip()
        if not name or not value:
            continue
        pairs.append(f"{name}={value}")
    return "; ".join(pairs)


def build_cookie_snapshot(cookies: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Serialize captured cookies into the local credential-file shape."""
    return {
        "cookies": {
            str(cookie.get("name") or "").strip(): str(cookie.get("value") or "").strip()
            for cookie in cookies
            if str(cookie.get("name") or "").strip() and str(cookie.get("value") or "").strip()
        }
    }


def build_auth_headers(auth_session: AIHRAuthSession | None) -> dict[str, str]:
    """Build request headers for AI-HR APIs."""
    headers: dict[str, str] = {}
    if auth_session is None:
        return headers
    access_token = str(auth_session.access_token or "").strip()
    if access_token:
        headers["Authorization"] = access_token if access_token.lower().startswith("bearer ") else f"Bearer {access_token}"
    workspace_id = str(auth_session.workspace_id or "").strip()
    if workspace_id:
        headers["X-Workspace-Id"] = workspace_id
    return headers


def unwrap_envelope(response: httpx.Response, *, action: str) -> dict[str, Any]:
    """Validate the unified API envelope and return its data."""
    if response.status_code >= 400:
        message = (response.text or "").strip()
        raise RuntimeError(f"{action} failed with HTTP {response.status_code}: {message}")

    payload = response.json()
    if not payload.get("ok"):
        error = payload.get("error") or {}
        code = error.get("code") or "unknown_error"
        message = error.get("message") or "Unknown API error"
        raise RuntimeError(f"{action} failed: {code} {message}")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"{action} failed: response data is not an object")
    return data


def login_ai_hr(client: httpx.Client, *, email: str, password: str) -> AIHRAuthSession:
    """Login to AI-HR and return the issued auth session."""
    response = client.post("/auth/login", json={"email": email, "password": password})
    data = unwrap_envelope(response, action="AI-HR login")
    session_data = data.get("session") or {}
    access_token = str(session_data.get("access_token") or "").strip()
    if not access_token:
        raise RuntimeError("AI-HR login failed: access_token is missing from response")
    workspace_id = str(session_data.get("workspace_id") or "").strip() or None
    return AIHRAuthSession(access_token=access_token, workspace_id=workspace_id)


def update_boss_cookie(
    client: httpx.Client,
    *,
    cookie_header: str,
    account_name: str = "Primary Account",
    auth_session: AIHRAuthSession | None = None,
) -> dict[str, Any]:
    """Write the captured BOSS cookie into AI-HR."""
    response = client.post(
        "/credentials/boss",
        json={"cookie_header": cookie_header, "account_name": account_name},
        headers=build_auth_headers(auth_session),
    )
    return unwrap_envelope(response, action="Update BOSS credential")


def validate_boss_cookie(
    client: httpx.Client,
    *,
    auth_session: AIHRAuthSession | None = None,
) -> dict[str, Any]:
    """Validate the stored BOSS credential in AI-HR."""
    response = client.post(
        "/credentials/boss/validate",
        headers=build_auth_headers(auth_session),
    )
    return unwrap_envelope(response, action="Validate BOSS credential")
