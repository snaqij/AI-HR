"""In-memory runtime store for local development and fallback."""

from __future__ import annotations

import threading
import time
from typing import Any

from .store import InterviewRuntimeStore


class MemoryInterviewRuntimeStore(InterviewRuntimeStore):
    """Thread-safe in-memory runtime state store."""

    def __init__(self):
        self._lock = threading.Lock()
        self._store: dict[str, tuple[float, Any]] = {}

    def reserve_event(self, *, session_id: str, event_id: str, ttl_seconds: int) -> bool:
        key = f"idem:{session_id}:{event_id}"
        now = time.time()
        expire_at = now + max(1, int(ttl_seconds))
        with self._lock:
            self._gc_locked(now)
            if key in self._store:
                return False
            self._store[key] = (expire_at, "1")
            return True

    def save_question_pack(self, *, session_id: str, version: int, question_pack: dict[str, Any], ttl_seconds: int) -> None:
        expire_at = time.time() + max(1, int(ttl_seconds))
        key = f"qpack:{session_id}:v{version}"
        latest_key = f"qpack:{session_id}:latest"
        with self._lock:
            self._store[key] = (expire_at, dict(question_pack))
            self._store[latest_key] = (expire_at, int(version))

    def get_question_pack(self, *, session_id: str, version: int | None = None) -> dict[str, Any] | None:
        with self._lock:
            now = time.time()
            self._gc_locked(now)
            resolved_version = version
            if resolved_version is None:
                latest = self._store.get(f"qpack:{session_id}:latest")
                if latest is None:
                    return None
                resolved_version = int(latest[1])
            value = self._store.get(f"qpack:{session_id}:v{resolved_version}")
            if value is None:
                return None
            payload = value[1]
            return dict(payload) if isinstance(payload, dict) else None

    def init_session_state(self, *, session_id: str, state: dict[str, Any], ttl_seconds: int) -> None:
        expire_at = time.time() + max(1, int(ttl_seconds))
        with self._lock:
            self._store[f"state:{session_id}"] = (expire_at, dict(state))

    def get_session_state(self, *, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            now = time.time()
            self._gc_locked(now)
            item = self._store.get(f"state:{session_id}")
            if item is None:
                return None
            payload = item[1]
            return dict(payload) if isinstance(payload, dict) else None

    def patch_session_state(self, *, session_id: str, patch: dict[str, Any], ttl_seconds: int) -> dict[str, Any]:
        expire_at = time.time() + max(1, int(ttl_seconds))
        with self._lock:
            current = self._store.get(f"state:{session_id}")
            merged = dict(current[1]) if current and isinstance(current[1], dict) else {}
            merged.update(dict(patch))
            self._store[f"state:{session_id}"] = (expire_at, merged)
            return dict(merged)

    def save_prebuilt_pack(self, *, key: str, question_pack: dict[str, Any], ttl_seconds: int) -> None:
        expire_at = time.time() + max(1, int(ttl_seconds))
        with self._lock:
            self._store[f"prebuilt:{key}"] = (expire_at, dict(question_pack))

    def get_prebuilt_pack(self, *, key: str) -> dict[str, Any] | None:
        with self._lock:
            now = time.time()
            self._gc_locked(now)
            item = self._store.get(f"prebuilt:{key}")
            if item is None:
                return None
            payload = item[1]
            return dict(payload) if isinstance(payload, dict) else None

    def get_followup_cache(self, *, key: str) -> str | None:
        with self._lock:
            now = time.time()
            self._gc_locked(now)
            item = self._store.get(f"followup:{key}")
            if item is None:
                return None
            value = item[1]
            return str(value) if value is not None else None

    def set_followup_cache(self, *, key: str, value: str, ttl_seconds: int) -> None:
        expire_at = time.time() + max(1, int(ttl_seconds))
        with self._lock:
            self._store[f"followup:{key}"] = (expire_at, value)

    def _gc_locked(self, now: float) -> None:
        expired = [item_key for item_key, (expire_at, _) in self._store.items() if expire_at <= now]
        for item_key in expired:
            self._store.pop(item_key, None)

