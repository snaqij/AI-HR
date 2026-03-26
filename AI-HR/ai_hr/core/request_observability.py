"""Request-level trace id propagation and latency logging."""

from __future__ import annotations

import logging
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send


TRACE_HEADER = b"x-trace-id"
TRACE_SCOPE_KEY = "ai_hr.trace_id"


def _extract_trace_id(scope: Scope) -> str:
    for name, value in scope.get("headers", []):
        if name.lower() == TRACE_HEADER:
            incoming = value.decode("utf-8").strip()
            if incoming:
                return incoming
    return uuid.uuid4().hex


class RequestObservabilityMiddleware:
    """Attach `x-trace-id` to responses and emit request latency logs."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._logger = logging.getLogger("ai_hr.request")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        trace_id = _extract_trace_id(scope)
        scope[TRACE_SCOPE_KEY] = trace_id
        started = time.perf_counter()
        status_code = 500

        async def wrapped_send(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message.get("status", 500))
                headers = list(message.get("headers", []))
                if not any(name.lower() == TRACE_HEADER for name, _ in headers):
                    headers.append((TRACE_HEADER, trace_id.encode("utf-8")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        finally:
            latency_ms = max(1, int((time.perf_counter() - started) * 1000))
            self._logger.info(
                "request.completed method=%s path=%s status=%s latency_ms=%s trace_id=%s",
                scope.get("method", ""),
                scope.get("path", ""),
                status_code,
                latency_ms,
                trace_id,
            )

