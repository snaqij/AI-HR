"""LiveKit 401 diagnostics for AI-HR.

Usage:
  uv run --project AI-HR python AI-HR/scripts/livekit_401_diag.py
  uv run --project AI-HR python AI-HR/scripts/livekit_401_diag.py --env-file AI-HR/.env.dev
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path

# Allow importing ai_hr when running from repo root.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_hr.core.config import get_settings  # noqa: E402
from ai_hr.services.rtc.livekit_gateway import LiveKitConfig, LiveKitRTCGateway  # noqa: E402


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def _mask(value: str | None, *, head: int = 4, tail: int = 4) -> str:
    if not value:
        return "<empty>"
    if len(value) <= head + tail:
        return "*" * len(value)
    return f"{value[:head]}...{value[-tail:]}"


def _decode_jwt_payload(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    try:
        raw = base64.urlsafe_b64decode((payload + padding).encode("utf-8"))
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


def _print_result(result: CheckResult) -> None:
    mark = "PASS" if result.ok else "FAIL"
    print(f"[{mark}] {result.name}: {result.detail}")


def _run_create_room_probe(base_url: str, create_room_path: str, token: str, room_name: str, timeout_sec: float) -> CheckResult:
    url = f"{base_url.rstrip('/')}{create_room_path}"
    body = json.dumps({"name": room_name, "emptyTimeout": 60, "maxParticipants": 2}).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        method="POST",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            status = int(getattr(resp, "status", 200))
            payload = resp.read().decode("utf-8", errors="replace")
            if status >= 400:
                return CheckResult("CreateRoom API", False, f"HTTP {status}, body={payload[:300]}")
            return CheckResult("CreateRoom API", True, f"HTTP {status}, body={payload[:300]}")
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = "<unable to read error body>"
        hint = ""
        if exc.code == 401:
            hint = " -> likely key/secret mismatch, wrong project, or invalid signature"
        return CheckResult("CreateRoom API", False, f"HTTP {exc.code}, body={body[:500]}{hint}")
    except Exception as exc:
        return CheckResult("CreateRoom API", False, f"{type(exc).__name__}: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose LiveKit 401 issues")
    parser.add_argument("--env-file", default=None, help="Optional env file path (e.g. AI-HR/.env.dev)")
    parser.add_argument("--timeout", type=float, default=6.0, help="HTTP timeout seconds")
    args = parser.parse_args()

    if args.env_file:
        env_file = Path(args.env_file).resolve()
        os.environ["AI_HR_ENV_FILE"] = str(env_file)
        get_settings.cache_clear()

    settings = get_settings()

    print("=== LiveKit 401 Diagnostics ===")
    print(f"RTC_PROVIDER: {settings.rtc_provider}")
    print(f"LIVEKIT_BASE_URL: {settings.livekit_base_url}")
    print(f"LIVEKIT_API_KEY: {_mask(settings.livekit_api_key)}")
    print(f"LIVEKIT_API_SECRET: {_mask(settings.livekit_api_secret)}")
    print(f"CREATE_ROOM_PATH: {settings.livekit_create_room_path}")
    print()

    results: list[CheckResult] = []

    provider_ok = (settings.rtc_provider or "").strip().lower() == "livekit"
    results.append(CheckResult("rtc_provider", provider_ok, f"value={settings.rtc_provider!r}"))

    base_url = (settings.livekit_base_url or "").strip()
    url_ok = base_url.startswith("https://") and ".livekit." in base_url
    results.append(CheckResult("livekit_base_url format", url_ok, f"value={base_url!r} (expect https://...)"))

    key_ok = bool((settings.livekit_api_key or "").strip())
    secret_ok = bool((settings.livekit_api_secret or "").strip())
    results.append(CheckResult("livekit_api_key present", key_ok, _mask(settings.livekit_api_key)))
    results.append(CheckResult("livekit_api_secret present", secret_ok, _mask(settings.livekit_api_secret)))

    if provider_ok and url_ok and key_ok and secret_ok:
        cfg = LiveKitConfig(
            base_url=base_url,
            api_key=settings.livekit_api_key or "",
            api_secret=settings.livekit_api_secret or "",
            create_room_path=settings.livekit_create_room_path,
            update_subscriptions_path=settings.livekit_update_subscriptions_path,
            send_data_path=settings.livekit_send_data_path,
            room_prefix=settings.livekit_room_prefix,
            token_ttl_seconds=settings.rtc_token_ttl_seconds,
            timeout_seconds=max(1.0, args.timeout),
        )
        gateway = LiveKitRTCGateway(cfg)

        token = gateway._build_access_token(identity="diag-server", room="diag-room", room_admin=True)  # noqa: SLF001
        payload = _decode_jwt_payload(token)
        iss_ok = payload.get("iss") == (settings.livekit_api_key or "")
        exp_ok = isinstance(payload.get("exp"), int) and int(payload["exp"]) > int(time.time())
        video_ok = isinstance(payload.get("video"), dict) and payload["video"].get("roomJoin") is True
        room_create_ok = isinstance(payload.get("video"), dict) and payload["video"].get("roomCreate") is True
        room_admin_ok = isinstance(payload.get("video"), dict) and payload["video"].get("roomAdmin") is True
        results.append(CheckResult("JWT iss check", iss_ok, f"iss={payload.get('iss')!r}"))
        results.append(CheckResult("JWT exp check", exp_ok, f"exp={payload.get('exp')!r}"))
        results.append(CheckResult("JWT video grants", video_ok, f"video={payload.get('video')!r}"))
        results.append(CheckResult("JWT roomCreate grant", room_create_ok, f"roomCreate={payload.get('video', {}).get('roomCreate')!r}"))
        results.append(CheckResult("JWT roomAdmin grant", room_admin_ok, f"roomAdmin={payload.get('video', {}).get('roomAdmin')!r}"))

        probe = _run_create_room_probe(
            base_url=base_url,
            create_room_path=settings.livekit_create_room_path,
            token=token,
            room_name=f"diag-{uuid.uuid4().hex[:8]}",
            timeout_sec=max(1.0, args.timeout),
        )
        results.append(probe)

    print("--- Results ---")
    for item in results:
        _print_result(item)

    failures = [item for item in results if not item.ok]
    print()
    if failures:
        print("Conclusion: LIVEKIT config is NOT ready. Review FAIL items above.")
        return 1

    print("Conclusion: LIVEKIT config checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
