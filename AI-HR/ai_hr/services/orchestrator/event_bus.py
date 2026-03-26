"""Session-scoped websocket event bus for interview realtime updates."""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass
from typing import Any

from ...core.config import get_settings


@dataclass(slots=True)
class EventSubscription:
    session_id: str
    subscription_id: str
    queue: asyncio.Queue[dict[str, Any]]


class InterviewEventBus:
    def __init__(self):
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()
        self._subs: dict[str, dict[str, EventSubscription]] = {}

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        with self._lock:
            self._loop = loop

    def subscribe(self, *, session_id: str) -> EventSubscription:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=128)
        sub = EventSubscription(
            session_id=session_id,
            subscription_id=f"sub-{int(time.time() * 1000)}-{id(queue)}",
            queue=queue,
        )
        with self._lock:
            self._subs.setdefault(session_id, {})[sub.subscription_id] = sub
        return sub

    def unsubscribe(self, subscription: EventSubscription) -> None:
        with self._lock:
            session_map = self._subs.get(subscription.session_id)
            if not session_map:
                return
            session_map.pop(subscription.subscription_id, None)
            if not session_map:
                self._subs.pop(subscription.session_id, None)

    def publish(self, *, session_id: str, event_type: str, payload: dict[str, Any]) -> None:
        event = {
            "event_type": event_type,
            "session_id": session_id,
            "ts": int(time.time() * 1000),
            "payload": payload,
        }
        self._publish_local(event)

    def _publish_local(self, event: dict[str, Any]) -> None:
        session_id = str(event.get("session_id") or "")
        if not session_id:
            return
        with self._lock:
            loop = self._loop
            targets = list(self._subs.get(session_id, {}).values())
        if loop is None or not targets:
            return
        for sub in targets:
            loop.call_soon_threadsafe(self._put_safely, sub.queue, event)

    @staticmethod
    def _put_safely(queue: asyncio.Queue[dict[str, Any]], item: dict[str, Any]) -> None:
        if queue.full():
            try:
                queue.get_nowait()
            except Exception:
                pass
        queue.put_nowait(item)


def _build_default_event_bus() -> InterviewEventBus:
    settings = get_settings()
    if settings.ai_interview_redis_event_bus_enabled and settings.ai_interview_redis_enabled and (settings.redis_url or "").strip():
        try:
            from .event_bus_redis import RedisInterviewEventBus

            return RedisInterviewEventBus(
                redis_url=str(settings.redis_url).strip(),
                redis_prefix=settings.ai_interview_redis_prefix,
            )
        except Exception:
            return InterviewEventBus()
    return InterviewEventBus()


DEFAULT_INTERVIEW_EVENT_BUS = _build_default_event_bus()

