"""Follow-up cache implementations with optional redis runtime backend."""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass

from ...core.config import get_settings
from ..interview_runtime.factory import get_interview_runtime_store


@dataclass(frozen=True, slots=True)
class FollowupCacheEntry:
    question: str
    reason: str | None
    created_at: float


class FollowupCache:
    def __init__(self, *, ttl_seconds: int = 180, max_entries: int = 1024):
        self._ttl = max(30, int(ttl_seconds))
        self._max_entries = max(128, int(max_entries))
        self._lock = threading.Lock()
        self._store: dict[str, FollowupCacheEntry] = {}

    def build_key(
        self,
        *,
        stage: str,
        language: str,
        transcript: str,
        question_id: str | None = None,
        session_id: str | None = None,
    ) -> str:
        normalized = " ".join(transcript.strip().split())[:320]
        material = f"{session_id or '-'}|{question_id or '-'}|{stage}|{language}|{normalized}".encode("utf-8")
        return hashlib.sha256(material).hexdigest()[:40]

    def get(self, key: str) -> FollowupCacheEntry | None:
        now = time.time()
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            if now - item.created_at > self._ttl:
                self._store.pop(key, None)
                return None
            return item

    def set(self, key: str, *, question: str, reason: str | None = None) -> None:
        now = time.time()
        entry = FollowupCacheEntry(question=question, reason=reason, created_at=now)
        with self._lock:
            if len(self._store) >= self._max_entries:
                oldest_key = min(self._store, key=lambda item_key: self._store[item_key].created_at)
                self._store.pop(oldest_key, None)
            self._store[key] = entry


class RedisFollowupCache:
    """Cache backed by interview runtime store."""

    def __init__(self, *, ttl_seconds: int = 180):
        self._ttl = max(30, int(ttl_seconds))
        self._store = get_interview_runtime_store()

    def build_key(
        self,
        *,
        stage: str,
        language: str,
        transcript: str,
        question_id: str | None = None,
        session_id: str | None = None,
    ) -> str:
        normalized = " ".join(transcript.strip().split())[:320]
        material = f"{session_id or '-'}|{question_id or '-'}|{stage}|{language}|{normalized}".encode("utf-8")
        return hashlib.sha256(material).hexdigest()[:40]

    def get(self, key: str) -> FollowupCacheEntry | None:
        value = self._store.get_followup_cache(key=key)
        if not value:
            return None
        return FollowupCacheEntry(question=value, reason="redis", created_at=time.time())

    def set(self, key: str, *, question: str, reason: str | None = None) -> None:
        self._store.set_followup_cache(key=key, value=question, ttl_seconds=self._ttl)


def create_default_followup_cache():
    settings = get_settings()
    ttl = int(settings.ai_interview_followup_cache_ttl_seconds)
    if settings.ai_interview_redis_enabled and (settings.redis_url or "").strip():
        try:
            return RedisFollowupCache(ttl_seconds=ttl)
        except Exception:
            return FollowupCache(ttl_seconds=ttl)
    return FollowupCache(ttl_seconds=ttl)


DEFAULT_FOLLOWUP_CACHE = create_default_followup_cache()
