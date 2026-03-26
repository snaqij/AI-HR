"""Redis-backed interview event bus for multi-instance fanout."""

from __future__ import annotations

import json
import threading
import time
import uuid
from typing import Any

from .event_bus import InterviewEventBus


class RedisInterviewEventBus(InterviewEventBus):
    """Publish to local subscribers and Redis pub/sub channels."""

    def __init__(self, *, redis_url: str, redis_prefix: str = "aihr"):
        super().__init__()
        try:
            from redis import Redis
        except Exception as exc:  # pragma: no cover - environment dependent
            raise RuntimeError("redis package is not installed") from exc
        self._instance_id = uuid.uuid4().hex[:12]
        self._redis_prefix = (redis_prefix or "aihr").strip()
        self._channel_base = f"{self._redis_prefix}:intv:events"
        self._client = Redis.from_url(redis_url, decode_responses=True)
        self._listener_thread = threading.Thread(target=self._reader_loop, daemon=True, name="aihr-redis-eventbus")
        self._listener_thread.start()

    def publish(self, *, session_id: str, event_type: str, payload: dict[str, Any]) -> None:
        event = {
            "event_type": event_type,
            "session_id": session_id,
            "ts": int(time.time() * 1000),
            "payload": payload,
            "_bus_instance_id": self._instance_id,
        }
        self._publish_local(event)
        try:
            self._client.publish(self._channel_for_session(session_id), json.dumps(event, ensure_ascii=False))
        except Exception:
            # Keep local bus alive even if redis publish fails.
            return

    def _reader_loop(self) -> None:
        try:
            pubsub = self._client.pubsub(ignore_subscribe_messages=True)
            pubsub.psubscribe(f"{self._channel_base}:*")
            for message in pubsub.listen():
                if not isinstance(message, dict):
                    continue
                raw = message.get("data")
                if not raw:
                    continue
                try:
                    event = json.loads(str(raw))
                except Exception:
                    continue
                if not isinstance(event, dict):
                    continue
                if str(event.get("_bus_instance_id") or "") == self._instance_id:
                    continue
                self._publish_local(event)
        except Exception:
            # Ignore listener failures; default in-process bus still works.
            return

    def _channel_for_session(self, session_id: str) -> str:
        return f"{self._channel_base}:{session_id}"

