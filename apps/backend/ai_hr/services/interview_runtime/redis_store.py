"""Redis-backed runtime store implementation."""

from __future__ import annotations

import json
from typing import Any

from .store import InterviewRuntimeStore


class RedisInterviewRuntimeStore(InterviewRuntimeStore):
    """Redis implementation for hot interview runtime state."""

    def __init__(self, *, redis_url: str, prefix: str = "aihr"):
        try:
            from redis import Redis
        except Exception as exc:  # pragma: no cover - exercised in environments without redis package
            raise RuntimeError("redis package is not installed") from exc
        self._prefix = (prefix or "aihr").strip()
        self._client = Redis.from_url(redis_url, decode_responses=True)

    def reserve_event(self, *, session_id: str, event_id: str, ttl_seconds: int) -> bool:
        key = self._k("idem", session_id, event_id)
        return bool(self._client.set(key, "1", ex=max(1, int(ttl_seconds)), nx=True))

    def save_question_pack(self, *, session_id: str, version: int, question_pack: dict[str, Any], ttl_seconds: int) -> None:
        ex = max(1, int(ttl_seconds))
        payload = json.dumps(question_pack, ensure_ascii=False)
        pack_key = self._k("qpack", session_id, f"v{int(version)}")
        latest_key = self._k("qpack", session_id, "latest")
        pipe = self._client.pipeline()
        pipe.set(pack_key, payload, ex=ex)
        pipe.set(latest_key, int(version), ex=ex)
        pipe.execute()

    def get_question_pack(self, *, session_id: str, version: int | None = None) -> dict[str, Any] | None:
        resolved_version = version
        if resolved_version is None:
            latest_key = self._k("qpack", session_id, "latest")
            latest_raw = self._client.get(latest_key)
            if not latest_raw:
                return None
            resolved_version = int(latest_raw)
        raw = self._client.get(self._k("qpack", session_id, f"v{int(resolved_version)}"))
        return self._loads_dict(raw)

    def init_session_state(self, *, session_id: str, state: dict[str, Any], ttl_seconds: int) -> None:
        key = self._k("state", session_id)
        self._client.set(key, json.dumps(state, ensure_ascii=False), ex=max(1, int(ttl_seconds)))

    def get_session_state(self, *, session_id: str) -> dict[str, Any] | None:
        key = self._k("state", session_id)
        raw = self._client.get(key)
        return self._loads_dict(raw)

    def patch_session_state(self, *, session_id: str, patch: dict[str, Any], ttl_seconds: int) -> dict[str, Any]:
        key = self._k("state", session_id)
        current = self._loads_dict(self._client.get(key)) or {}
        current.update(dict(patch))
        self._client.set(key, json.dumps(current, ensure_ascii=False), ex=max(1, int(ttl_seconds)))
        return current

    def save_prebuilt_pack(self, *, key: str, question_pack: dict[str, Any], ttl_seconds: int) -> None:
        redis_key = self._k("prebuilt", key)
        self._client.set(redis_key, json.dumps(question_pack, ensure_ascii=False), ex=max(1, int(ttl_seconds)))

    def get_prebuilt_pack(self, *, key: str) -> dict[str, Any] | None:
        raw = self._client.get(self._k("prebuilt", key))
        return self._loads_dict(raw)

    def get_followup_cache(self, *, key: str) -> str | None:
        raw = self._client.get(self._k("followup", key))
        return str(raw) if raw is not None else None

    def set_followup_cache(self, *, key: str, value: str, ttl_seconds: int) -> None:
        self._client.set(self._k("followup", key), value, ex=max(1, int(ttl_seconds)))

    def _k(self, *parts: str) -> str:
        body = ":".join(str(item).strip() for item in parts if str(item).strip())
        return f"{self._prefix}:intv:{body}"

    @staticmethod
    def _loads_dict(raw: str | None) -> dict[str, Any] | None:
        if not raw:
            return None
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                return payload
        except Exception:
            return None
        return None

