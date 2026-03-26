"""Runtime store abstractions for AI interview hot state."""

from __future__ import annotations

from typing import Any, Protocol


class InterviewRuntimeStore(Protocol):
    """Protocol for Redis-backed or in-memory runtime data."""

    def reserve_event(self, *, session_id: str, event_id: str, ttl_seconds: int) -> bool:
        """Reserve an event idempotency key. Return True when newly reserved."""

    def save_question_pack(self, *, session_id: str, version: int, question_pack: dict[str, Any], ttl_seconds: int) -> None:
        """Persist a question pack snapshot."""

    def get_question_pack(self, *, session_id: str, version: int | None = None) -> dict[str, Any] | None:
        """Fetch a question pack snapshot by version or latest."""

    def init_session_state(self, *, session_id: str, state: dict[str, Any], ttl_seconds: int) -> None:
        """Initialize the hot runtime state for a session."""

    def get_session_state(self, *, session_id: str) -> dict[str, Any] | None:
        """Read hot runtime state."""

    def patch_session_state(self, *, session_id: str, patch: dict[str, Any], ttl_seconds: int) -> dict[str, Any]:
        """Patch and return the merged state."""

    def save_prebuilt_pack(self, *, key: str, question_pack: dict[str, Any], ttl_seconds: int) -> None:
        """Save prebuilt question pack by deterministic key."""

    def get_prebuilt_pack(self, *, key: str) -> dict[str, Any] | None:
        """Read prebuilt question pack by deterministic key."""

    def get_followup_cache(self, *, key: str) -> str | None:
        """Get followup cache entry text."""

    def set_followup_cache(self, *, key: str, value: str, ttl_seconds: int) -> None:
        """Set followup cache entry text."""

