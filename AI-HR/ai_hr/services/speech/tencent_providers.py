"""Tencent Cloud speech providers (ASR/TTS)."""

from __future__ import annotations

import logging
import base64

logger = logging.getLogger(__name__)

import hashlib
import hmac
import json
import random
import re
import threading
import time
import queue
import urllib.error
import urllib.parse
import urllib.request
import uuid
import wave
from dataclasses import dataclass, field
from io import BytesIO
from collections.abc import Iterable

from ...core.exceptions import ConnectorOperationError, InvalidConnectorConfigError
from .base import ASRProvider, ASRStreamResult, TTSProvider, TTSStreamResult


@dataclass(slots=True)
class _DuplexASRContext:
    ws: object
    transcripts: list[str] = field(default_factory=list)
    last_transcript: str = ""
    last_active_at: float = field(default_factory=time.time)


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _build_tc3_headers(
    *,
    secret_id: str,
    secret_key: str,
    service: str,
    host: str,
    action: str,
    version: str,
    region: str,
    payload: str,
) -> dict[str, str]:
    algorithm = "TC3-HMAC-SHA256"
    timestamp = str(int(time.time()))
    date = time.strftime("%Y-%m-%d", time.gmtime(int(timestamp)))
    content_type = "application/json; charset=utf-8"

    canonical_headers = (
        f"content-type:{content_type}\n"
        f"host:{host}\n"
        f"x-tc-action:{action.lower()}\n"
    )
    signed_headers = "content-type;host;x-tc-action"
    hashed_request_payload = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    canonical_request = f"POST\n/\n\n{canonical_headers}\n{signed_headers}\n{hashed_request_payload}"

    credential_scope = f"{date}/{service}/tc3_request"
    string_to_sign = (
        f"{algorithm}\n{timestamp}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
    )

    secret_date = _sign(f"TC3{secret_key}".encode("utf-8"), date)
    secret_service = _sign(secret_date, service)
    secret_signing = _sign(secret_service, "tc3_request")
    signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    authorization = (
        f"{algorithm} "
        f"Credential={secret_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )

    return {
        "Authorization": authorization,
        "Content-Type": content_type,
        "Host": host,
        "X-TC-Action": action,
        "X-TC-Version": version,
        "X-TC-Region": region,
        "X-TC-Timestamp": timestamp,
    }


class TencentASRProvider(ASRProvider):
    provider_name = "tencent"

    def __init__(
        self,
        *,
        secret_id: str,
        secret_key: str,
        region: str,
        timeout_ms: int,
        engine_type: str = "16k_zh",
        voice_format: int = 4,
        endpoint: str = "https://asr.tencentcloudapi.com",
        app_id: str | None = None,
        ws_base_url: str = "wss://asr.cloud.tencent.com/asr/v2",
        streaming_enabled: bool = True,
        ws_allow_http_fallback: bool = True,
        ws_expire_seconds: int = 90,
        ws_session_ttl_seconds: int = 45,
        ws_partial_wait_ms: int = 35,
        ws_final_wait_ms: int = 800,
        ws_open_timeout_ms: int = 800,
        ws_single_connection_enabled: bool = True,
        prewarm_enabled: bool = True,
        keepalive_interval_seconds: int = 8,
        keepalive_pcm_ms: int = 40,
        force_streaming: bool = False,
        hotword_file: str | None = None,
    ):
        if not secret_id or not secret_key:
            raise InvalidConnectorConfigError("Tencent ASR provider requires secret_id/secret_key")
        self._secret_id = secret_id
        self._secret_key = secret_key
        self._region = region
        self._timeout = max(1.0, timeout_ms / 1000.0)
        self._engine_type = engine_type
        self._voice_format = voice_format
        self._endpoint = endpoint.rstrip("/")
        self._app_id = str(app_id or "").strip()
        self._ws_base_url = ws_base_url.rstrip("/")
        self._streaming_enabled = bool(streaming_enabled)
        self._ws_allow_http_fallback = bool(ws_allow_http_fallback)
        self._ws_expire_seconds = max(30, int(ws_expire_seconds))
        self._ws_session_ttl_seconds = max(10, int(ws_session_ttl_seconds))
        self._ws_partial_wait_seconds = max(0.01, int(ws_partial_wait_ms) / 1000.0)
        self._ws_final_wait_seconds = max(0.01, int(ws_final_wait_ms) / 1000.0)
        self._ws_open_timeout_seconds = max(0.2, int(ws_open_timeout_ms) / 1000.0)
        self._ws_single_connection_enabled = bool(ws_single_connection_enabled)
        self._prewarm_enabled = bool(prewarm_enabled)
        self._keepalive_interval_seconds = max(2, int(keepalive_interval_seconds))
        self._keepalive_pcm_ms = max(20, int(keepalive_pcm_ms))
        self._force_streaming = bool(force_streaming)

        self._hotword_list = ""
        if hotword_file:
            try:
                import os
                if os.path.exists(hotword_file):
                    with open(hotword_file, "r", encoding="utf-8") as f:
                        lines = [line.strip() for line in f if line.strip()]
                        self._hotword_list = ",".join(lines)
            except Exception as exc:
                logger.warning(f"Failed to load hotword file {hotword_file}: {exc}")
        self._ws_contexts: dict[str, _DuplexASRContext] = {}
        self._ws_lock = threading.Lock()
        self._stream_mutexes: dict[str, threading.Lock] = {}
        self._stream_mutexes_lock = threading.Lock()

    def warmup(self, *, session_id: str) -> None:
        if not self._prewarm_enabled:
            return
        if not self._streaming_enabled or not self._app_id:
            return
        try:
            from websockets.sync.client import connect as ws_connect
        except Exception:
            return

        stream_key = session_id if self._ws_single_connection_enabled else f"{session_id}:0"
        try:
            ctx, _ = self._ensure_ws_context(stream_key=stream_key, ws_connect=ws_connect)
            # 16k/16bit/mono PCM silence warmup.
            silence_bytes = b"\x00\x00" * int(16000 * self._keepalive_pcm_ms / 1000)
            if silence_bytes:
                ctx.ws.send(silence_bytes)
            self._collect_ws_messages(ctx=ctx, wait_for_final=False, timeout_seconds=0.03)
            ctx.last_active_at = time.time()
        except Exception:
            self._close_ws_context(stream_key)

    def transcribe_stream(
        self,
        *,
        session_id: str,
        seq: int,
        text_hint: str,
        audio_base64: str | None,
        confidence: float,
        latency_ms: int,
        chunk_index: int = 1,
        chunk_total: int = 1,
        is_final: bool = True,
        voice_format: str | None = None,
    ) -> ASRStreamResult:
        if not audio_base64:
            transcript = text_hint.strip() or f"ASR_TRANSCRIPT_SEQ_{seq}"
            return ASRStreamResult(transcript=transcript, confidence=confidence, latency_ms=latency_ms, provider=self.provider_name)

        if self._force_streaming and (not self._streaming_enabled or not self._app_id):
            raise ConnectorOperationError("Tencent ASR force_streaming enabled but streaming/AppID is not configured")

        if self._streaming_enabled and self._app_id:
            try:
                return self._transcribe_stream_ws_duplex(
                    session_id=session_id,
                    seq=seq,
                    text_hint=text_hint,
                    audio_base64=audio_base64,
                    confidence=confidence,
                    chunk_index=chunk_index,
                    chunk_total=chunk_total,
                    is_final=is_final,
                    voice_format=voice_format,
                )
            except Exception as exc:
                if self._force_streaming or (not self._ws_allow_http_fallback):
                    raise
                # Keep production availability when websocket path is temporarily unavailable.
                return self._transcribe_stream_http(
                    session_id=session_id,
                    seq=seq,
                    text_hint=text_hint,
                    audio_base64=audio_base64,
                    confidence=confidence,
                    fallback_reason=str(exc),
                )

        if self._force_streaming:
            raise ConnectorOperationError("Tencent ASR force_streaming enabled but websocket streaming path unavailable")

        return self._transcribe_stream_http(
            session_id=session_id,
            seq=seq,
            text_hint=text_hint,
            audio_base64=audio_base64,
            confidence=confidence,
            fallback_reason="ws_disabled_or_missing_app_id",
        )

    def _transcribe_stream_ws_duplex(
        self,
        *,
        session_id: str,
        seq: int,
        text_hint: str,
        audio_base64: str,
        confidence: float,
        chunk_index: int,
        chunk_total: int,
        is_final: bool,
        voice_format: str | None = None,
    ) -> ASRStreamResult:
        try:
            from websockets.sync.client import connect as ws_connect
        except Exception as exc:  # pragma: no cover - depends on runtime install
            raise ConnectorOperationError("Tencent ASR websocket mode requires dependency 'websockets'") from exc

        stream_key = session_id if self._ws_single_connection_enabled else f"{session_id}:{seq}"
        stream_mutex = self._get_stream_mutex(stream_key)
        audio_bytes = self._decode_audio_bytes_for_stream(audio_base64)
        call_start = time.perf_counter()
        with stream_mutex:
            self._cleanup_stale_ws_contexts()
            last_exc: Exception | None = None
            partial_texts: list[str] = []
            before_len = 0
            ctx: _DuplexASRContext | None = None
            connection_reused = False
            reconnect_count = 0
            for attempt in range(2):
                logger.debug("Tencent ASR WS duplex: attempt=%s, stream_key=%s", attempt, stream_key)
                ctx, connection_reused = self._ensure_ws_context(
                    stream_key=stream_key,
                    ws_connect=ws_connect,
                    voice_format=voice_format
                )
                logger.debug(
                    "Tencent ASR WS duplex: stream_key=%s, connection_reused=%s, ctx_last_active_at=%s",
                    stream_key, connection_reused, ctx.last_active_at
                )
                try:
                    if connection_reused and (time.time() - ctx.last_active_at) >= self._keepalive_interval_seconds:
                        logger.debug("Tencent ASR WS duplex: sending keepalive for stream_key=%s", stream_key)
                        self._send_keepalive(ctx)
                    before_len = len(ctx.transcripts)
                    if audio_bytes:
                        # Pacing logic: split large audio and ensure we stay under 3s/s limit.
                        # Limit is 3s audio per 1s wall time.
                        # For 16k PCM, 100ms = 3200 bytes.
                        chunk_size = 3200
                        pacing_start = time.perf_counter()
                        audio_duration_sent = 0.0
                        
                        for i in range(0, len(audio_bytes), chunk_size):
                            chunk = audio_bytes[i : i + chunk_size]
                            ctx.ws.send(chunk)
                            audio_duration_sent += len(chunk) / 32000.0  # 16k mono 16bit
                            
                            # Calculate if we are exceeding the 3s/s rate.
                            # Time needed = duration / 3.0
                            elapsed = time.perf_counter() - pacing_start
                            wall_time_needed = audio_duration_sent / 3.0
                            if wall_time_needed > elapsed:
                                # We are sending too fast, wait a bit.
                                # Use a small buffer to allow slight bursts.
                                time.sleep(min(0.2, wall_time_needed - elapsed))

                        logger.debug("Tencent ASR WS duplex: sent %d bytes in %.3fs", len(audio_bytes), time.perf_counter() - pacing_start)
                    partial_texts, _ = self._collect_ws_messages(
                        ctx=ctx,
                        wait_for_final=False,
                        timeout_seconds=self._ws_partial_wait_seconds,
                    )
                    if is_final or chunk_index >= chunk_total:
                        if self._ws_single_connection_enabled:
                            final_texts, _ = self._collect_ws_messages(
                                ctx=ctx,
                                wait_for_final=True,
                                timeout_seconds=min(self._timeout, self._ws_final_wait_seconds),
                            )
                            partial_texts.extend(final_texts)
                        else:
                            ctx.ws.send(json.dumps({"type": "end"}, ensure_ascii=False))
                            final_texts, _ = self._collect_ws_messages(
                                ctx=ctx, wait_for_final=True, timeout_seconds=self._timeout
                            )
                            partial_texts.extend(final_texts)
                            self._close_ws_context(stream_key)
                    last_exc = None
                    logger.info(
                        "Tencent ASR WS duplex: stream_key=%s, is_final=%s, partial_texts=%s, new_transcripts_count=%d",
                        stream_key, is_final, partial_texts, len(ctx.transcripts) - before_len
                    )
                    logger.debug(
                        "tencent_asr.ws_stream stream_key=%s is_final=%s new_transcripts=%s partials=%s",
                        stream_key,
                        is_final,
                        len(ctx.transcripts) - before_len,
                        len(partial_texts),
                    )
                    break
                except Exception as exc:
                    last_exc = exc
                    self._close_ws_context(stream_key)
                    should_retry = attempt == 0 and self._is_recoverable_ws_error(exc)
                    if should_retry:
                        reconnect_count += 1
                        continue
                    raise ConnectorOperationError(f"Tencent ASR websocket error: {exc}") from exc
            if last_exc is not None or ctx is None:
                raise ConnectorOperationError(f"Tencent ASR websocket error: {last_exc or 'unknown'}")

            new_transcripts = ctx.transcripts[before_len:]
            transcript = self._pick_latest_transcript(
                new_transcripts,
                partial_texts,
                cached_transcript=ctx.last_transcript,
                text_hint=text_hint,
                seq=seq,
            )
            if transcript:
                ctx.last_transcript = transcript
            return ASRStreamResult(
                transcript=transcript,
                confidence=confidence,
                latency_ms=max(1, int((time.perf_counter() - call_start) * 1000)),
                provider=f"{self.provider_name}_ws_duplex",
                metadata={
                    "connection_reused": bool(connection_reused),
                    "reconnect_count": int(reconnect_count),
                    "stream_key_mode": "session" if self._ws_single_connection_enabled else "session_seq",
                },
            )

    def _get_stream_mutex(self, stream_key: str) -> threading.Lock:
        with self._stream_mutexes_lock:
            lock = self._stream_mutexes.get(stream_key)
            if lock is None:
                lock = threading.Lock()
                self._stream_mutexes[stream_key] = lock
            return lock

    def _ensure_ws_context(self, *, stream_key: str, ws_connect, voice_format: str | None = None) -> tuple[_DuplexASRContext, bool]:  # noqa: ANN001
        with self._ws_lock:
            ctx = self._ws_contexts.get(stream_key)
            reused = ctx is not None
            if ctx is None:
                ws_url = self._build_ws_url(voice_id=stream_key, voice_format=voice_format)
                logger.debug("tencent_asr.ws_url stream_key=%s ws_url=%s", stream_key, ws_url)
                
                # Force IPv4 to avoid 5.2s Windows IPv6 TCP SYN timeout
                import socket
                orig_getaddrinfo = socket.getaddrinfo
                def ipv4_getaddrinfo(host, port, family=0, *args, **kwargs):
                    return orig_getaddrinfo(host, port, socket.AF_INET, *args, **kwargs)
                
                socket.getaddrinfo = ipv4_getaddrinfo
                try:
                    ws_instance = ws_connect(
                        ws_url,
                        open_timeout=self._ws_open_timeout_seconds,
                        close_timeout=1,
                        max_size=8 * 1024 * 1024,
                    )
                finally:
                    socket.getaddrinfo = orig_getaddrinfo
                    
                ctx = _DuplexASRContext(ws=ws_instance)
                self._ws_contexts[stream_key] = ctx
            ctx.last_active_at = time.time()
            return ctx, reused

    def _send_keepalive(self, ctx: _DuplexASRContext) -> None:
        silence_bytes = b"\x00\x00" * int(16000 * self._keepalive_pcm_ms / 1000)
        if silence_bytes:
            ctx.ws.send(silence_bytes)
        self._collect_ws_messages(ctx=ctx, wait_for_final=False, timeout_seconds=0.02)
        ctx.last_active_at = time.time()

    def _transcribe_stream_http(
        self,
        *,
        session_id: str,
        seq: int,
        text_hint: str,
        audio_base64: str,
        confidence: float,
        fallback_reason: str,
    ) -> ASRStreamResult:
        data_bytes = self._decode_audio_bytes(audio_base64)
        request_payload = {
            "ProjectId": 0,
            "EngSerViceType": self._engine_type,
            "SourceType": 1,
            "VoiceFormat": self._normalize_voice_format(self._voice_format),
            "Data": audio_base64,
            "DataLen": len(data_bytes),
            "UsrAudioKey": f"{session_id}-{seq}",
        }
        body = json.dumps(request_payload, ensure_ascii=False, separators=(",", ":"))
        host = self._endpoint.replace("https://", "").replace("http://", "")
        headers = _build_tc3_headers(
            secret_id=self._secret_id,
            secret_key=self._secret_key,
            service="asr",
            host=host,
            action="SentenceRecognition",
            version="2019-06-14",
            region=self._region,
            payload=body,
        )
        request = urllib.request.Request(
            url=f"{self._endpoint}/",
            method="POST",
            data=body.encode("utf-8"),
            headers=headers,
        )
        call_start = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ConnectorOperationError(f"Tencent ASR HTTP error: {exc.code}") from exc
        except Exception as exc:  # pragma: no cover
            raise ConnectorOperationError(f"Tencent ASR error: {exc}") from exc

        response_payload = payload.get("Response", {}) if isinstance(payload, dict) else {}
        response_error = response_payload.get("Error") if isinstance(response_payload, dict) else None
        if isinstance(response_error, dict):
            err_code = str(response_error.get("Code") or "UnknownError")
            err_msg = str(response_error.get("Message") or "unknown tencent asr error")
            raise ConnectorOperationError(f"Tencent ASR business error: {err_code} - {err_msg}")

        transcript = str(response_payload.get("Result") or text_hint or "")
        provider_suffix = f"{self.provider_name}_http_fallback" if fallback_reason else self.provider_name
        return ASRStreamResult(
            transcript=transcript,
            confidence=confidence,
            latency_ms=max(1, int((time.perf_counter() - call_start) * 1000)),
            provider=provider_suffix,
        )

    def _build_ws_url(self, *, voice_id: str, voice_format: str | None = None) -> str:
        timestamp = int(time.time())
        expired = timestamp + self._ws_expire_seconds
        nonce = random.randint(10000, 99999)
        v_format = voice_format or self._voice_format
        params: dict[str, str | int] = {
            "secretid": self._secret_id,
            "timestamp": timestamp,
            "expired": expired,
            "nonce": nonce,
            "engine_model_type": self._engine_type,
            "voice_id": voice_id,
            "voice_format": 1 if self._normalize_voice_format(v_format) == "pcm" else 4,
            "needvad": 0,
            "filter_dirty": 0,
            "filter_modal": 0,
            "convert_num_mode": 1,
            "word_info": 0,
        }
        if self._hotword_list:
            params["hotword_list"] = self._hotword_list
        ordered_items = sorted((k, str(v)) for k, v in params.items())
        query = "&".join(f"{k}={urllib.parse.quote(v, safe='')}" for k, v in ordered_items)
        path = f"/asr/v2/{self._app_id}"
        sign_source = f"asr.cloud.tencent.com{path}?{query}"
        signature = base64.b64encode(hmac.new(self._secret_key.encode("utf-8"), sign_source.encode("utf-8"), hashlib.sha1).digest())
        signature_enc = urllib.parse.quote(signature.decode("utf-8"), safe="")
        return f"{self._ws_base_url}/{self._app_id}?{query}&signature={signature_enc}"

    def _collect_ws_messages(
        self, *, ctx: _DuplexASRContext, wait_for_final: bool, timeout_seconds: float
    ) -> tuple[list[str], bool]:
        deadline = time.perf_counter() + max(0.01, timeout_seconds)
        texts: list[str] = []
        reached_final = False
        while time.perf_counter() < deadline:
            remaining = max(0.01, deadline - time.perf_counter())
            try:
                message = ctx.ws.recv(timeout=remaining)
            except TimeoutError:
                break
                break
            except Exception:
                break
            
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Tencent ASR WS msg: {message}")

            payload = self._parse_ws_message(message)
            code = payload.get("code")
            if code is not None and code != 0:
                logger.warning("tencent_asr.ws_business_error code=%s message=%s", code, payload.get("message"))
            
            text = self._extract_ws_text(payload)
            if text:
                ctx.transcripts.append(text)
                texts.append(text)
            if wait_for_final and self._is_ws_final(payload):
                reached_final = True
                break
        return texts, reached_final

    def _cleanup_stale_ws_contexts(self) -> None:
        now = time.time()
        stale_keys: list[str] = []
        with self._ws_lock:
            for key, ctx in self._ws_contexts.items():
                if now - ctx.last_active_at >= self._ws_session_ttl_seconds:
                    stale_keys.append(key)
        for key in stale_keys:
            self._close_ws_context(key)

    def _close_ws_context(self, stream_key: str) -> None:
        with self._ws_lock:
            ctx = self._ws_contexts.pop(stream_key, None)
        if ctx is None:
            return
        try:
            ctx.ws.close()
        except Exception:
            return

    @staticmethod
    def _decode_audio_bytes(audio_base64: str) -> bytes:
        try:
            return base64.b64decode(audio_base64.encode("utf-8"), validate=False)
        except Exception:
            return audio_base64.encode("utf-8")

    def _decode_audio_bytes_for_stream(self, audio_base64: str) -> bytes:
        data = self._decode_audio_bytes(audio_base64)
        if self._normalize_voice_format(self._voice_format) == "pcm" and self._looks_like_wav(data):
            pcm = self._extract_pcm_from_wav(data)
            if pcm:
                return pcm
        return data

    @staticmethod
    def _looks_like_wav(data: bytes) -> bool:
        return len(data) >= 12 and data[0:4] == b"RIFF" and data[8:12] == b"WAVE"

    @staticmethod
    def _extract_pcm_from_wav(data: bytes) -> bytes:
        try:
            with wave.open(BytesIO(data), "rb") as wf:
                return wf.readframes(wf.getnframes())
        except Exception:
            return data

    @staticmethod
    def _parse_ws_message(message: str | bytes) -> dict:
        if isinstance(message, bytes):
            text = message.decode("utf-8", errors="ignore")
        else:
            text = message
        try:
            payload = json.loads(text)
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _extract_ws_text(payload: dict) -> str:
        result = payload.get("result")
        if isinstance(result, dict):
            for key in ("voice_text_str", "text", "result_text"):
                value = result.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        for key in ("voice_text_str", "text", "result_text"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @staticmethod
    def _is_ws_final(payload: dict) -> bool:
        if payload.get("final") in {1, True, "1", "true"}:
            return True
        if payload.get("final_result") in {1, True, "1", "true"}:
            return True
        code = payload.get("code")
        return code in {0, "0"} and payload.get("message") in {"success", "finished"}

    @staticmethod
    def _is_recoverable_ws_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return (
            "connectionclosed" in message
            or "no close frame received or sent" in message
            or "connection is closed" in message
            or "broken pipe" in message
            or "ssleoferror" in message
            or "eof occurred in violation of protocol" in message
        )

    @staticmethod
    def _pick_latest_transcript(
        transcripts: Iterable[str],
        partial_texts: Iterable[str],
        *,
        cached_transcript: str,
        text_hint: str,
        seq: int,
    ) -> str:
        cleaned_partial = [item.strip() for item in partial_texts if item and item.strip()]
        if cleaned_partial:
            return cleaned_partial[-1]
        cleaned = [item.strip() for item in transcripts if item and item.strip()]
        if cleaned:
            return cleaned[-1]
        if cached_transcript.strip():
            return cached_transcript.strip()
        fallback = text_hint.strip()
        return text_hint.strip()

    @staticmethod
    def _normalize_voice_format(value: int | str) -> str:
        raw = str(value).strip().lower()
        if raw in {"wav", "pcm", "mp3", "silk"}:
            return raw
        if raw == "4":
            return "wav"
        if raw == "1":
            return "pcm"
        return "wav"


class TencentTTSProvider(TTSProvider):
    provider_name = "tencent"

    def __init__(
        self,
        *,
        secret_id: str,
        secret_key: str,
        region: str,
        timeout_ms: int,
        app_id: str | None = None,
        voice_type: int = 101001,
        sample_rate: int = 16000,
        codec: str = "pcm",
        endpoint: str = "https://tts.tencentcloudapi.com",
        ws_base_url: str = "wss://tts.cloud.tencent.com/stream_wsv2",
        ws_streaming_enabled: bool = True,
        ws_allow_http_fallback: bool = False,
        ws_expire_seconds: int = 90,
        ws_open_timeout_ms: int = 1200,
        ws_recv_timeout_ms: int = 1200,
        first_chunk_size: int = 12,
        warmup_enabled: bool = True,
    ):
        if not secret_id or not secret_key:
            raise InvalidConnectorConfigError("Tencent TTS provider requires secret_id/secret_key")
        self._secret_id = secret_id
        self._secret_key = secret_key
        self._region = region
        self._timeout = max(1.0, timeout_ms / 1000.0)
        self._app_id = str(app_id or "").strip()
        self._voice_type = voice_type
        self._sample_rate = sample_rate
        requested_codec = str(codec or "").strip().lower()
        if requested_codec and requested_codec != "pcm":
            logger.warning("Tencent TTS codec '%s' is not low-latency safe here; forcing codec=pcm", requested_codec)
        self._codec = "pcm"
        self._endpoint = endpoint.rstrip("/")
        self._ws_base_url = ws_base_url.rstrip("/")
        self._ws_streaming_enabled = bool(ws_streaming_enabled)
        self._ws_allow_http_fallback = bool(ws_allow_http_fallback)
        self._ws_expire_seconds = max(30, int(ws_expire_seconds))
        self._ws_open_timeout_seconds = max(0.2, int(ws_open_timeout_ms) / 1000.0)
        self._ws_recv_timeout_seconds = max(0.2, int(ws_recv_timeout_ms) / 1000.0)
        self._first_chunk_size = max(8, int(first_chunk_size))
        self._warmup_enabled = bool(warmup_enabled)
        self._warm_cache: dict[str, float] = {}
        
        # Pre-warmed Connection Pool (Fresh connections, not reused)
        self._ws_pool = queue.Queue(maxsize=2)
        self._pool_stop_event = threading.Event()
        self._refiller_thread = threading.Thread(target=self._pool_refill_loop, daemon=True)
        self._refiller_thread.start()

    def _pool_refill_loop(self):
        """Background thread that keeps fresh, authenticated connections ready."""
        try:
            from websockets.sync.client import connect as ws_connect
        except ImportError:
            return

        while not self._pool_stop_event.is_set():
            if self._ws_pool.full():
                time.sleep(0.5)
                continue
            
            try:
                ws_url = self._build_tts_ws_url()
                # 禁用内置 ping_interval，防止后台心跳超时抛错（由我们自己通过获取时的 ws.ping() 管理）
                ws = ws_connect(
                    ws_url, 
                    open_timeout=self._ws_open_timeout_seconds,
                    ping_interval=None
                )
                
                # Consume initial ready packet to make it 'hot'
                ready_deadline = time.perf_counter() + 0.5
                is_ready = False
                while time.perf_counter() < ready_deadline:
                    try:
                        msg = ws.recv(timeout=0.05)
                        if isinstance(msg, (bytes, bytearray)):
                            is_ready = True
                            break
                        payload = self._parse_ws_json(msg)
                        if payload.get("ready") in {1, True, "1", "true"}:
                            is_ready = True
                            break
                    except Exception:
                        break
                
                if is_ready:
                    self._ws_pool.put(ws, timeout=1.0)
                    logger.debug("[Tencent TTS Pool] Pre-warmed a fresh connection. Current pool size: %d", self._ws_pool.qsize())
                else:
                    try: ws.close()
                    except Exception: pass
            except Exception as e:
                logger.debug("[Tencent TTS Pool] Failed to pre-warm: %s", e)
                time.sleep(2.0) # Backoff on error

    def warmup(self, *, session_id: str, voice: str) -> None:
        if not self._warmup_enabled:
            return
        key = f"{voice}:{session_id[:8]}"
        self._warm_cache[key] = time.time()

    def _acquire_ws(self, ws_connect):
        """Acquire a pre-warmed WebSocket from the pool or create a new one."""
        while not self._ws_pool.empty():
            try:
                ws = self._ws_pool.get(timeout=0.01)
                # 优化：不再使用阻塞式的 ws.ping()，因为它会增加 50-100ms 的网络往返延迟。
                # 改为直接返回，如果发送数据时报错，由 synthesization 逻辑重试。
                logger.debug("[Tencent TTS Pool] Using pre-warmed WebSocket (ping-check skipped for latency).")
                return ws, True
            except queue.Empty:
                break

        # Fallback if pool is empty
        ws_url = self._build_tts_ws_url()
        logger.debug("[Tencent TTS Pool] No valid pre-warmed WS. Fallback to SYNC handshake.")
        ws = ws_connect(
            ws_url, 
            open_timeout=self._ws_open_timeout_seconds,
            ping_interval=None
        )
        return ws, False

    def _release_ws(self, ws):
        """Once used, close the WebSocket session as Tencent doesn't support session reuse."""
        try:
            if ws: ws.close()
        except Exception:
            pass


    def synthesize_stream(
        self,
        *,
        session_id: str,
        text: str,
        voice: str,
        chunk_size: int,
    ) -> TTSStreamResult:
        chunks = self._split_text_chunks(text=text, chunk_size=chunk_size)
        audio_uris = [item["audio_uri"] for item in self.synthesize_stream_iter(session_id=session_id, text=text, voice=voice, chunk_size=chunk_size)]
        return TTSStreamResult(chunks=chunks, audio_uris=audio_uris, provider=self.provider_name)

    def synthesize_stream_iter(
        self,
        *,
        session_id: str,
        text: str,
        voice: str,
        chunk_size: int,
    ):
        if self._ws_streaming_enabled:
            try:
                yield from self._synthesize_stream_iter_ws(
                    session_id=session_id,
                    text=text,
                    voice=voice,
                    chunk_size=chunk_size,
                )
                return
            except Exception as exc:
                if not self._ws_allow_http_fallback:
                    raise
                logger.warning("Tencent TTS websocket stream failed; fallback to HTTP TextToVoice: %s", exc)

        yield from self._synthesize_stream_iter_http(
            session_id=session_id,
            text=text,
            voice=voice,
            chunk_size=chunk_size,
        )

    def _synthesize_stream_iter_http(
        self,
        *,
        session_id: str,
        text: str,
        voice: str,
        chunk_size: int,
    ):
        _ = voice
        chunks = self._split_text_chunks(text=text, chunk_size=chunk_size)
        host = self._endpoint.replace("https://", "").replace("http://", "")
        total = len(chunks)
        for idx, chunk in enumerate(chunks, start=1):
            request_payload = {
                "Text": chunk,
                "SessionId": f"{session_id}-{idx}-{uuid.uuid4().hex[:8]}",
                "ModelType": 1,
                "VoiceType": self._voice_type,
                "SampleRate": self._sample_rate,
                "Codec": self._codec,
            }
            body = json.dumps(request_payload, ensure_ascii=False, separators=(",", ":"))
            headers = _build_tc3_headers(
                secret_id=self._secret_id,
                secret_key=self._secret_key,
                service="tts",
                host=host,
                action="TextToVoice",
                version="2019-08-23",
                region=self._region,
                payload=body,
            )
            request = urllib.request.Request(
                url=f"{self._endpoint}/",
                method="POST",
                data=body.encode("utf-8"),
                headers=headers,
            )
            try:
                with urllib.request.urlopen(request, timeout=self._timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                raise ConnectorOperationError(f"Tencent TTS HTTP error: {exc.code}") from exc
            except Exception as exc:  # pragma: no cover
                raise ConnectorOperationError(f"Tencent TTS error: {exc}") from exc

            response_payload = payload.get("Response", {}) if isinstance(payload, dict) else {}
            response_error = response_payload.get("Error") if isinstance(response_payload, dict) else None
            if isinstance(response_error, dict):
                err_code = str(response_error.get("Code") or "UnknownError")
                err_msg = str(response_error.get("Message") or "unknown tencent tts error")
                raise ConnectorOperationError(f"Tencent TTS business error: {err_code} - {err_msg}")
            audio_base64 = str(response_payload.get("Audio") or "")
            if not audio_base64:
                request_id = str(response_payload.get("RequestId") or "")
                raise ConnectorOperationError(
                    f"Tencent TTS response missing audio payload (request_id={request_id}, payload_keys={list(response_payload.keys())})"
                )
            audio_bytes = base64.b64decode(audio_base64)
            if self._codec == "pcm" and self._looks_like_mp3(audio_bytes):
                request_id = str(response_payload.get("RequestId") or "")
                raise ConnectorOperationError(
                    f"Tencent TTS codec mismatch: expected pcm but got mp3-like payload (request_id={request_id})"
                )
            yield {
                "index": idx,
                "audio_uri": "",  # BE-013: Skip heavy Base64/DataURI encoding in the hot loop
                "audio_bytes": audio_bytes,
                "audio_codec": str(self._codec or "").lower(),
                "sample_rate": int(self._sample_rate),
                "text": chunk,
                "is_final_packet": idx == total,
            }

    def _synthesize_stream_iter_ws(
        self,
        *,
        session_id: str,
        text: str,
        voice: str,
        chunk_size: int,
    ) -> Iterable[dict]:
        try:
            from websockets.sync.client import connect as ws_connect
        except ImportError as exc:
            raise ConnectorOperationError("Tencent TTS websocket mode requires dependency 'websockets'") from exc

        start_time = time.perf_counter()
        stream_session_id = f"tts-{session_id}-{uuid.uuid4().hex[:8]}"
        chunks = self._split_text_chunks(text=text, chunk_size=chunk_size)
        
        packet_idx = 0
        last_yield_text = text
        pending_audio = None
        ws = None
        connection_reused = False

        try:
            # Use connection pool!
            ws, connection_reused = self._acquire_ws(ws_connect)

            # If it's a new connection, we MUST consume the initial "ready" packet.
            if not connection_reused:
                ready_deadline = time.perf_counter() + 0.35
                while time.perf_counter() < ready_deadline:
                    try:
                        msg = ws.recv(timeout=0.05)
                        if isinstance(msg, (bytes, bytearray)):
                            if msg: pending_audio = bytes(msg)
                            break
                        payload = self._parse_ws_json(msg)
                        if payload.get("code") not in (None, 0, "0"):
                            raise RuntimeError(f"Tencent TTS ready error: {payload.get('message')}")
                        if payload.get("ready") in {1, True, "1", "true"}: break
                    except (TimeoutError, Exception):
                        pass

            # Send synthesis command
            for idx, chunk in enumerate(chunks, start=1):
                # We use a unique message_id per synthesis attempt even on reused connection
                task_id = f"{stream_session_id}-{idx}"
                ws.send(json.dumps({
                    "session_id": stream_session_id,
                    "message_id": task_id,
                    "action": "ACTION_SYNTHESIS",
                    "data": chunk,
                }, ensure_ascii=False))

            ws.send(json.dumps({
                "session_id": stream_session_id,
                "message_id": f"{stream_session_id}-complete",
                "action": "ACTION_COMPLETE",
                "data": "",
            }, ensure_ascii=False))

            finished = False
            while not finished:
                try:
                    message = ws.recv(timeout=self._ws_recv_timeout_seconds)
                except (TimeoutError, Exception) as exc:
                    # If timeout in pool, connection might be dead
                    raise ConnectorOperationError("Tencent TTS websocket recv timeout or connection lost") from exc

                if isinstance(message, (bytes, bytearray)):
                    audio_bytes = bytes(message)
                    if not audio_bytes: continue
                    
                    if pending_audio is None:
                        pending_audio = audio_bytes
                    else:
                        packet_idx += 1
                        yield {
                            "index": packet_idx,
                            "audio_bytes": pending_audio,
                            "audio_codec": str(self._codec or "").lower(),
                            "sample_rate": int(self._sample_rate),
                            "text": last_yield_text,
                            "is_final_packet": False,
                        }
                        pending_audio = audio_bytes
                else:
                    payload = self._parse_ws_json(message)
                    if payload.get("code") not in (None, 0, "0"):
                        raise ConnectorOperationError(f"Tencent TTS business error: {payload.get('message')}")
                    if payload.get("final") in {1, True, "1", "true"}:
                        finished = True

            if pending_audio:
                packet_idx += 1
                yield {
                    "index": packet_idx,
                    "audio_bytes": pending_audio,
                    "audio_codec": str(self._codec or "").lower(),
                    "sample_rate": int(self._sample_rate),
                    "text": last_yield_text,
                    "is_final_packet": True,
                }
            
            # Release back to pool!
            self._release_ws(ws)
            ws = None

        except Exception as exc:
            if ws:
                try: ws.close()
                except Exception: pass
            raise ConnectorOperationError(f"Tencent TTS websocket error: {exc}") from exc
        finally:
            if ws:
                try: ws.close()
                except Exception: pass

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        logger.debug("Tencent TTS websocket stream finished session=%s packets=%s elapsed_ms=%s", session_id, packet_idx, elapsed_ms)

    def _build_tts_ws_url(self) -> str:
        parsed = urllib.parse.urlparse(self._ws_base_url if "://" in self._ws_base_url else f"wss://{self._ws_base_url}")
        scheme = parsed.scheme or "wss"
        host = parsed.netloc or "tts.cloud.tencent.com"
        path = parsed.path or "/stream_wsv2"
        now = int(time.time())
        expired = now + self._ws_expire_seconds

        params: dict[str, str | int] = {
            "Action": "TextToStreamAudioWSv2",
            "AppId": self._app_id,
            "Codec": self._codec,
            "EnableSubtitle": 1,
            "Expired": expired,
            "ModelType": 1,
            "SampleRate": int(self._sample_rate),
            "SecretId": self._secret_id,
            "SessionId": f"tts-{uuid.uuid4().hex[:16]}",
            "Speed": 0,
            "Timestamp": now,
            "VoiceType": int(self._voice_type),
            "Volume": 0,
        }
        ordered = sorted((k, str(v)) for k, v in params.items())
        query = "&".join(f"{k}={urllib.parse.quote(v, safe='')}" for k, v in ordered)
        sign_source = f"GET{host}{path}?{query}"
        signature = base64.b64encode(
            hmac.new(self._secret_key.encode("utf-8"), sign_source.encode("utf-8"), hashlib.sha1).digest()
        ).decode("utf-8")
        return f"{scheme}://{host}{path}?{query}&Signature={urllib.parse.quote(signature, safe='')}"

    @staticmethod
    def _parse_ws_json(message: str | bytes) -> dict:
        if isinstance(message, bytes):
            text = message.decode("utf-8", errors="ignore")
        else:
            text = str(message or "")
        try:
            payload = json.loads(text)
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _looks_like_mp3(audio_bytes: bytes) -> bool:
        if not audio_bytes:
            return False
        # Strict mode:
        # 1) ID3 tag is a definitive MP3 signature.
        # 2) Otherwise require two consecutive valid MPEG frame headers with
        #    parseable frame lengths to avoid false-positive on random PCM bytes.
        if audio_bytes.startswith(b"ID3"):
            return True
        if len(audio_bytes) < 8:
            return False

        first_len = TencentTTSProvider._mp3_frame_length(audio_bytes, 0)
        if first_len <= 0:
            return False
        second_off = first_len
        if second_off + 4 > len(audio_bytes):
            return False
        second_len = TencentTTSProvider._mp3_frame_length(audio_bytes, second_off)
        return second_len > 0

    @staticmethod
    def _mp3_frame_length(data: bytes, offset: int) -> int:
        if offset + 4 > len(data):
            return -1
        b0, b1, b2, b3 = data[offset], data[offset + 1], data[offset + 2], data[offset + 3]
        # Sync bits: 11 ones
        if b0 != 0xFF or (b1 & 0xE0) != 0xE0:
            return -1
        # MPEG Version / Layer / Bitrate / SampleRate must be valid.
        version_id = (b1 >> 3) & 0x03
        layer = (b1 >> 1) & 0x03
        bitrate_idx = (b2 >> 4) & 0x0F
        sample_rate_idx = (b2 >> 2) & 0x03
        padding = (b2 >> 1) & 0x01
        if version_id == 0x01 or layer == 0x00:
            return -1
        if bitrate_idx in (0x00, 0x0F) or sample_rate_idx == 0x03:
            return -1

        # Table: MPEG1 Layer III and MPEG2/2.5 Layer III bitrates (kbps).
        bitrate_table_v1_l3 = [
            0, 32, 40, 48, 56, 64, 80, 96,
            112, 128, 160, 192, 224, 256, 320, 0,
        ]
        bitrate_table_v2_l3 = [
            0, 8, 16, 24, 32, 40, 48, 56,
            64, 80, 96, 112, 128, 144, 160, 0,
        ]
        sample_rates = {
            0x00: [11025, 22050, 44100],  # MPEG2.5, MPEG2, MPEG1
            0x01: [12000, 24000, 48000],
            0x02: [8000, 16000, 32000],
        }
        # version_id: 00->2.5, 10->2, 11->1
        if version_id == 0x03:
            version_col = 2
            bitrate_kbps = bitrate_table_v1_l3[bitrate_idx]
        else:
            version_col = 0 if version_id == 0x00 else 1
            bitrate_kbps = bitrate_table_v2_l3[bitrate_idx]
        sample_rate = sample_rates[sample_rate_idx][version_col]
        if bitrate_kbps <= 0 or sample_rate <= 0:
            return -1

        # Layer III frame length formula.
        if version_id == 0x03:  # MPEG1
            frame_len = int((144000 * bitrate_kbps) / sample_rate) + padding
        else:  # MPEG2/2.5
            frame_len = int((72000 * bitrate_kbps) / sample_rate) + padding
        return frame_len if frame_len > 0 else -1

    def _pcm_bytes_to_wav_data_uri(self, pcm_bytes: bytes) -> str:
        buf = BytesIO()
        with wave.open(buf, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)  # 16-bit PCM
            wav.setframerate(int(self._sample_rate))
            wav.writeframes(pcm_bytes)
        wav_bytes = buf.getvalue()
        return f"data:audio/wav;base64,{base64.b64encode(wav_bytes).decode('ascii')}"

    def _split_text_chunks(self, *, text: str, chunk_size: int) -> list[str]:
        normalized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text).strip()
        if not normalized:
            return [text.strip()]

        first_size = min(max(8, self._first_chunk_size), max(8, chunk_size))
        chunks: list[str] = []
        head = normalized[:first_size].strip()
        if head:
            chunks.append(head)

        remain = normalized[first_size:]
        body_chunks = [remain[idx : idx + chunk_size].strip() for idx in range(0, len(remain), chunk_size)]
        for item in body_chunks:
            if not item:
                continue
            if len(item) <= 3 and chunks:
                chunks[-1] = f"{chunks[-1]}{item}"
                continue
            chunks.append(item)
        return chunks or [normalized]
