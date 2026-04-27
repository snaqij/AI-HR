"""Session-scoped websocket event bus for interview realtime updates."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

from ...core.config import get_settings

logger = logging.getLogger(__name__)


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
        self._drop_total = 0
        self._drop_by_session: dict[str, int] = {}
        self._drop_by_subscription: dict[str, int] = {}

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        with self._lock:
            self._loop = loop

    def subscribe(self, *, session_id: str) -> EventSubscription:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=512)
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
            drop_total = self._drop_by_subscription.get(subscription.subscription_id, 0)
        if drop_total:
            logger.info(
                "interview.event_bus.unsubscribe_drop_summary session_id=%s subscription_id=%s dropped=%s",
                subscription.session_id,
                subscription.subscription_id,
                drop_total,
            )

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
            # Debug hook reserved for empty-target diagnostics.
            return
        # Silencing noisy publishing logs for production-like use
        # Debug hook reserved for fanout diagnostics.
        for sub in targets:
            loop.call_soon_threadsafe(
                self._put_safely,
                sub.queue,
                event,
                sub.session_id,
                sub.subscription_id,
            )

    def _put_safely(
        self,
        queue: asyncio.Queue[dict[str, Any]],
        item: dict[str, Any],
        session_id: str,
        subscription_id: str,
    ) -> None:
        dropped = False
        if queue.full():
            try:
                queue.get_nowait()
                dropped = True
            except Exception:
                pass
        try:
            queue.put_nowait(item)
        except asyncio.QueueFull:
            dropped = True
            try:
                queue.get_nowait()
            except Exception:
                pass
            try:
                queue.put_nowait(item)
            except Exception:
                return

        if not dropped:
            return

        with self._lock:
            self._drop_total += 1
            self._drop_by_session[session_id] = self._drop_by_session.get(session_id, 0) + 1
            self._drop_by_subscription[subscription_id] = self._drop_by_subscription.get(subscription_id, 0) + 1
            drop_total = self._drop_total
            drop_session = self._drop_by_session[session_id]
            drop_sub = self._drop_by_subscription[subscription_id]

        if drop_total <= 5 or drop_total % 50 == 0:
            logger.warning(
                "interview.event_bus.queue_drop session_id=%s subscription_id=%s event_type=%s "
                "queue_size=%s drop_total=%s session_drop_total=%s subscription_drop_total=%s",
                session_id,
                subscription_id,
                str(item.get("event_type") or ""),
                queue.qsize(),
                drop_total,
                drop_session,
                drop_sub,
            )

    def get_drop_stats_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "drop_total": self._drop_total,
                "drop_by_session": dict(self._drop_by_session),
                "drop_by_subscription": dict(self._drop_by_subscription),
            }


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

