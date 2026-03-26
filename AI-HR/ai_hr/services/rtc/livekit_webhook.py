"""LiveKit webhook token verification helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time


class LiveKitWebhookAuthError(ValueError):
    """Raised when livekit webhook token is missing or invalid."""


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("utf-8"))


def _extract_bearer_token(authorization: str | None) -> str:
    value = (authorization or "").strip()
    if len(value) < 8 or value[:7].lower() != "bearer ":
        raise LiveKitWebhookAuthError("Missing bearer token in Authorization header")
    token = value[7:].strip()
    if not token:
        raise LiveKitWebhookAuthError("Missing bearer token in Authorization header")
    return token


def verify_livekit_webhook_token(
    *,
    authorization: str | None,
    api_secret: str,
    expected_api_key: str | None = None,
    accept_skew_seconds: int = 120,
    now_ts: int | None = None,
) -> dict:
    """Verify HS256 webhook token and return decoded claims payload."""
    if not api_secret:
        raise LiveKitWebhookAuthError("LiveKit API secret is not configured")
    token = _extract_bearer_token(authorization)
    parts = token.split(".")
    if len(parts) != 3:
        raise LiveKitWebhookAuthError("Invalid JWT format")

    header_b64, payload_b64, signature_b64 = parts
    try:
        header = json.loads(_b64url_decode(header_b64).decode("utf-8"))
        claims = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        raise LiveKitWebhookAuthError("Invalid JWT payload") from exc

    if str(header.get("alg") or "").upper() != "HS256":
        raise LiveKitWebhookAuthError("Unsupported JWT algorithm")

    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    expected_sig = hmac.new(api_secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    expected_sig_b64 = base64.urlsafe_b64encode(expected_sig).rstrip(b"=").decode("utf-8")
    if not hmac.compare_digest(expected_sig_b64, signature_b64):
        raise LiveKitWebhookAuthError("Invalid webhook signature")

    now = int(now_ts or time.time())
    leeway = max(0, int(accept_skew_seconds))
    if expected_api_key:
        issuer = str(claims.get("iss") or "").strip()
        if issuer != expected_api_key:
            raise LiveKitWebhookAuthError("Unexpected webhook issuer")
    if "nbf" in claims and int(claims["nbf"]) > now + leeway:
        raise LiveKitWebhookAuthError("Webhook token is not active yet")
    if "exp" in claims and int(claims["exp"]) < now - leeway:
        raise LiveKitWebhookAuthError("Webhook token has expired")
    return claims if isinstance(claims, dict) else {}
