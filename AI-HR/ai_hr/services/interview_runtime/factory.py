"""Factory for selecting interview runtime store implementation."""

from __future__ import annotations

from functools import lru_cache

from ...core.config import get_settings
from .memory_store import MemoryInterviewRuntimeStore
from .redis_store import RedisInterviewRuntimeStore
from .store import InterviewRuntimeStore


@lru_cache
def get_interview_runtime_store() -> InterviewRuntimeStore:
    """Return redis store when enabled and healthy, otherwise memory fallback."""
    settings = get_settings()
    if settings.ai_interview_redis_enabled and (settings.redis_url or "").strip():
        try:
            return RedisInterviewRuntimeStore(
                redis_url=str(settings.redis_url).strip(),
                prefix=settings.ai_interview_redis_prefix,
            )
        except Exception:
            return MemoryInterviewRuntimeStore()
    return MemoryInterviewRuntimeStore()

