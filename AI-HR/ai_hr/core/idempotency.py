"""写操作幂等中间件。"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send


IDEMPOTENCY_HEADER = b"x-idempotency-key"


@dataclass(slots=True)
class CachedResponse:
    """用于幂等重放的缓存响应。"""

    request_fingerprint: str
    status_code: int
    headers: list[tuple[bytes, bytes]]
    body: bytes
    created_at: float


class InMemoryIdempotencyStore:
    """线程安全的内存幂等存储。"""

    def __init__(self, ttl_seconds: int = 24 * 60 * 60) -> None:
        """按 TTL 初始化存储。"""
        self._ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._records: dict[str, CachedResponse | None] = {}

    def reserve_or_get(self, key: str) -> CachedResponse | None | str:
        """保留 key，或返回已缓存响应/处理中状态。"""
        with self._lock:
            self._cleanup_locked()
            existing = self._records.get(key)
            if existing is None and key in self._records:
                return "in_progress"
            if existing is not None:
                return existing
            self._records[key] = None
            return None

    def commit(self, key: str, response: CachedResponse) -> None:
        """提交完成响应到幂等缓存。"""
        with self._lock:
            self._records[key] = response

    def rollback(self, key: str) -> None:
        """请求失败时回滚保留的 key。"""
        with self._lock:
            self._records.pop(key, None)

    def _cleanup_locked(self) -> None:
        """清理过期缓存记录。"""
        now = time.time()
        expired = [
            key
            for key, value in self._records.items()
            if value is not None and now - value.created_at > self._ttl_seconds
        ]
        for key in expired:
            self._records.pop(key, None)


def _normalize_headers(raw_headers: list[tuple[bytes, bytes]]) -> dict[bytes, bytes]:
    """将请求头规范为小写键字典。"""
    normalized: dict[bytes, bytes] = {}
    for name, value in raw_headers:
        normalized[name.lower()] = value
    return normalized


def _extract_key(scope: Scope) -> str | None:
    """从请求头提取幂等键。"""
    headers = _normalize_headers(scope.get("headers", []))
    value = headers.get(IDEMPOTENCY_HEADER)
    if value is None:
        return None
    decoded = value.decode("utf-8").strip()
    return decoded or None


def _is_write_request(scope: Scope) -> bool:
    """判断是否为写请求方法。"""
    return scope["method"].upper() in {"POST", "PUT", "PATCH", "DELETE"}


def _compute_idempotency_digest(scope: Scope, body: bytes) -> str:
    """计算请求指纹（方法+路径+查询+体摘要）。"""
    method = scope["method"].upper()
    path = scope.get("path", "")
    query_string = scope.get("query_string", b"").decode("utf-8")
    body_digest = hashlib.sha256(body).hexdigest()
    return f"{method}:{path}?{query_string}:{body_digest}"


def _failure_payload(code: str, message: str) -> bytes:
    """构造统一失败响应体字节串。"""
    return json.dumps(
        {
            "ok": False,
            "schema_version": "1",
            "data": None,
            "error": {"code": code, "message": message},
        }
    ).encode("utf-8")


class IdempotencyMiddleware:
    """为写请求提供幂等语义的 ASGI 中间件。"""

    def __init__(self, app: ASGIApp, ttl_seconds: int = 24 * 60 * 60) -> None:
        """初始化中间件与内存存储。"""
        self.app = app
        self.store = InMemoryIdempotencyStore(ttl_seconds=ttl_seconds)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """执行幂等控制：重放、冲突校验、缓存成功响应。"""
        if scope["type"] != "http" or not _is_write_request(scope):
            await self.app(scope, receive, send)
            return

        idempotency_key = _extract_key(scope)
        if not idempotency_key:
            await self.app(scope, receive, send)
            return

        body = await self._read_body(receive)
        fingerprint = _compute_idempotency_digest(scope, body)
        cached_or_state = self.store.reserve_or_get(idempotency_key)
        if isinstance(cached_or_state, CachedResponse):
            if cached_or_state.request_fingerprint != fingerprint:
                await self._send_response(
                    send,
                    status_code=409,
                    headers=[(b"content-type", b"application/json")],
                    body=_failure_payload("idempotency_conflict", "Idempotency key was reused with a different request payload"),
                )
                return
            await self._send_response(send, cached_or_state.status_code, cached_or_state.headers, cached_or_state.body)
            return
        if cached_or_state == "in_progress":
            await self._send_response(
                send,
                status_code=409,
                headers=[(b"content-type", b"application/json")],
                body=_failure_payload("idempotency_in_progress", "Request with this idempotency key is still being processed"),
            )
            return

        status_code = 500
        response_headers: list[tuple[bytes, bytes]] = []
        response_chunks: list[bytes] = []

        async def wrapped_receive() -> Message:
            nonlocal body
            chunk = body
            body = b""
            return {"type": "http.request", "body": chunk, "more_body": False}

        async def wrapped_send(message: Message) -> None:
            nonlocal status_code, response_headers
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_headers = list(message.get("headers", []))
                return
            if message["type"] == "http.response.body":
                response_chunks.append(message.get("body", b""))
                return
            await send(message)

        try:
            await self.app(scope, wrapped_receive, wrapped_send)
            response_body = b"".join(response_chunks)
            await self._send_response(send, status_code, response_headers, response_body)
            if status_code < 500:
                self.store.commit(
                    idempotency_key,
                    CachedResponse(
                        request_fingerprint=fingerprint,
                        status_code=status_code,
                        headers=response_headers,
                        body=response_body,
                        created_at=time.time(),
                    ),
                )
            else:
                self.store.rollback(idempotency_key)
        except Exception:
            self.store.rollback(idempotency_key)
            raise

    async def _read_body(self, receive: Receive) -> bytes:
        """从 ASGI 通道完整读取请求体。"""
        chunks: list[bytes] = []
        while True:
            message = await receive()
            if message["type"] != "http.request":
                continue
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        return b"".join(chunks)

    async def _send_response(
        self,
        send: Send,
        status_code: int,
        headers: list[tuple[bytes, bytes]],
        body: bytes,
    ) -> None:
        """向 ASGI 发送完整 HTTP 响应。"""
        fixed_headers = self._normalize_response_headers(headers, body)
        await send({"type": "http.response.start", "status": status_code, "headers": fixed_headers})
        await send({"type": "http.response.body", "body": body, "more_body": False})

    def _normalize_response_headers(self, headers: list[tuple[bytes, bytes]], body: bytes) -> list[tuple[bytes, bytes]]:
        """确保 content-length 与响应体长度一致。"""
        names = {name.lower() for name, _ in headers}
        filtered = [(name, value) for name, value in headers if name.lower() != b"content-length"]
        if b"content-length" not in names:
            filtered.append((b"content-length", str(len(body)).encode("ascii")))
        else:
            filtered.append((b"content-length", str(len(body)).encode("ascii")))
        return filtered
