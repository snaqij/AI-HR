"""Security helpers for password hashing and signed tokens."""

from __future__ import annotations
import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from .config import get_settings


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def normalize_email(value: str) -> str:
    """Normalize email for stable uniqueness checks."""
    return str(value or "").strip().lower()


def sha256_hex(value: str) -> str:
    """Hash arbitrary secret material into fixed-length hex."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def generate_random_token(byte_len: int = 32) -> str:
    """Generate url-safe random tokens."""
    return secrets.token_urlsafe(max(16, byte_len))


def hash_password(password: str, *, iterations: int | None = None) -> str:
    """Create PBKDF2-SHA256 password hash with random salt."""
    settings = get_settings()
    rounds = int(iterations or settings.auth_password_pbkdf2_iterations)
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return f"pbkdf2_sha256${rounds}${_b64url_encode(salt)}${_b64url_encode(digest)}"


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against stored PBKDF2 digest."""
    try:
        algo, rounds_raw, salt_b64, digest_b64 = str(hashed).split("$", 3)
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    try:
        rounds = int(rounds_raw)
        salt = _b64url_decode(salt_b64)
        expected_digest = _b64url_decode(digest_b64)
    except Exception:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return hmac.compare_digest(expected_digest, actual)


@dataclass(slots=True)
class SignedTokenPayload:
    """Decoded signed token payload."""

    token_type: str
    session_id: str
    user_id: str
    exp: int


def build_signed_token(
    *,
    token_type: str,
    session_id: str,
    user_id: str,
    exp: int,
    nonce: str | None = None,
) -> str:
    """Build an HMAC signed token without external JWT dependency."""
    settings = get_settings()
    payload = {
        "typ": token_type,
        "sid": session_id,
        "uid": user_id,
        "exp": int(exp),
    }
    if nonce:
        payload["n"] = str(nonce)
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    signature = hmac.new(
        settings.auth_token_signing_key.encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"v1.{payload_b64}.{_b64url_encode(signature)}"


def parse_signed_token(token: str) -> SignedTokenPayload | None:
    """Validate and decode signed token payload."""
    settings = get_settings()
    try:
        prefix, payload_b64, signature_b64 = str(token or "").split(".", 2)
    except ValueError:
        return None
    if prefix != "v1":
        return None
    expected_sig = hmac.new(
        settings.auth_token_signing_key.encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).digest()
    try:
        provided_sig = _b64url_decode(signature_b64)
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception:
        return None
    if not hmac.compare_digest(expected_sig, provided_sig):
        return None
    try:
        token_type = str(payload["typ"])
        session_id = str(payload["sid"])
        user_id = str(payload["uid"])
        exp = int(payload["exp"])
    except Exception:
        return None
    now_ts = int(datetime.now(UTC).timestamp())
    if exp <= now_ts:
        return None
    return SignedTokenPayload(token_type=token_type, session_id=session_id, user_id=user_id, exp=exp)
