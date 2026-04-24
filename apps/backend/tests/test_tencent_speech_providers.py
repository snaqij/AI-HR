from __future__ import annotations

import base64
import sys
import types
import wave
from io import BytesIO

import pytest

from ai_hr.services.speech.base import ASRStreamResult
from ai_hr.services.speech.tencent_providers import TencentASRProvider, TencentTTSProvider


def test_tencent_asr_build_ws_url_should_include_signature() -> None:
    provider = TencentASRProvider(
        secret_id="sid",
        secret_key="skey",
        region="ap-guangzhou",
        timeout_ms=5000,
        app_id="123456",
        streaming_enabled=True,
    )
    url = provider._build_ws_url(voice_id="s-1")  # noqa: SLF001
    assert url.startswith("wss://asr.cloud.tencent.com/asr/v2/123456?")
    assert "signature=" in url
    assert "engine_model_type=16k_zh" in url


def test_tencent_asr_should_fallback_to_http_when_ws_failed(monkeypatch) -> None:
    provider = TencentASRProvider(
        secret_id="sid",
        secret_key="skey",
        region="ap-guangzhou",
        timeout_ms=5000,
        app_id="123456",
        streaming_enabled=True,
        ws_allow_http_fallback=True,
    )

    def _fake_ws(**kwargs):  # noqa: ANN003
        raise RuntimeError("ws failed")

    def _fake_http(**kwargs):  # noqa: ANN003
        return ASRStreamResult(transcript="ok", confidence=0.9, latency_ms=88, provider="tencent_http_fallback")

    monkeypatch.setattr(provider, "_transcribe_stream_ws_duplex", _fake_ws)
    monkeypatch.setattr(provider, "_transcribe_stream_http", _fake_http)

    result = provider.transcribe_stream(
        session_id="s1",
        seq=1,
        text_hint="",
        audio_base64="UklGRg==",
        confidence=0.9,
        latency_ms=320,
        chunk_index=1,
        chunk_total=1,
        is_final=True,
    )
    assert result.transcript == "ok"
    assert result.provider == "tencent_http_fallback"


def test_tencent_asr_force_streaming_should_not_fallback_to_http(monkeypatch) -> None:
    provider = TencentASRProvider(
        secret_id="sid",
        secret_key="skey",
        region="ap-guangzhou",
        timeout_ms=5000,
        app_id="123456",
        streaming_enabled=True,
        ws_allow_http_fallback=True,
        force_streaming=True,
    )

    def _fake_ws(**kwargs):  # noqa: ANN003
        raise RuntimeError("ws failed")

    monkeypatch.setattr(provider, "_transcribe_stream_ws_duplex", _fake_ws)

    with pytest.raises(Exception):
        provider.transcribe_stream(
            session_id="s1",
            seq=1,
            text_hint="",
            audio_base64="UklGRg==",
            confidence=0.9,
            latency_ms=320,
            chunk_index=1,
            chunk_total=1,
            is_final=True,
        )


def test_tencent_tts_should_prioritize_first_chunk_size() -> None:
    provider = TencentTTSProvider(
        secret_id="sid",
        secret_key="skey",
        region="ap-guangzhou",
        timeout_ms=5000,
        first_chunk_size=10,
    )
    chunks = provider._split_text_chunks(text="Please describe a recent performance optimization you did and give quantified results.", chunk_size=24)  # noqa: SLF001
    assert len(chunks) >= 2
    assert len(chunks[0]) <= 10


def test_tencent_asr_duplex_should_reuse_and_close_context(monkeypatch) -> None:
    provider = TencentASRProvider(
        secret_id="sid",
        secret_key="skey",
        region="ap-guangzhou",
        timeout_ms=5000,
        app_id="123456",
        streaming_enabled=True,
        ws_allow_http_fallback=False,
        ws_single_connection_enabled=False,
    )

    class _FakeWS:
        def __init__(self):
            self.closed = False
            self.recv_count = 0

        def send(self, payload):  # noqa: ANN001
            _ = payload

        def recv(self, timeout=None):  # noqa: ANN001
            _ = timeout
            self.recv_count += 1
            if self.recv_count == 1:
                return {"result": {"voice_text_str": "first segment"}}
            if self.recv_count == 2:
                return {"result": {"voice_text_str": "complete sentence"}, "final": 1}
            raise TimeoutError()

        def close(self):
            self.closed = True

    fake_ws = _FakeWS()

    def _fake_connect(*args, **kwargs):  # noqa: ANN002,ANN003
        _ = args, kwargs
        return fake_ws

    fake_client = types.ModuleType("websockets.sync.client")
    fake_client.connect = _fake_connect  # type: ignore[attr-defined]
    fake_sync = types.ModuleType("websockets.sync")
    fake_sync.client = fake_client  # type: ignore[attr-defined]
    fake_websockets = types.ModuleType("websockets")
    fake_websockets.sync = fake_sync  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "websockets", fake_websockets)
    monkeypatch.setitem(sys.modules, "websockets.sync", fake_sync)
    monkeypatch.setitem(sys.modules, "websockets.sync.client", fake_client)
    monkeypatch.setattr(provider, "_parse_ws_message", lambda x: x)

    first = provider.transcribe_stream(
        session_id="s1",
        seq=7,
        text_hint="",
        audio_base64="UklGRg==",
        confidence=0.9,
        latency_ms=100,
        chunk_index=1,
        chunk_total=2,
        is_final=False,
    )
    assert first.provider == "tencent_ws_duplex"
    assert first.transcript in {"first segment", "complete sentence"}
    assert len(provider._ws_contexts) == 1  # noqa: SLF001

    second = provider.transcribe_stream(
        session_id="s1",
        seq=7,
        text_hint="",
        audio_base64="UklGRg==",
        confidence=0.9,
        latency_ms=100,
        chunk_index=2,
        chunk_total=2,
        is_final=True,
    )
    assert second.provider == "tencent_ws_duplex"
    assert second.transcript == "complete sentence"
    assert len(provider._ws_contexts) == 0  # noqa: SLF001
    assert fake_ws.closed is True


def test_tencent_asr_duplex_should_keep_single_connection_across_seq(monkeypatch) -> None:
    provider = TencentASRProvider(
        secret_id="sid",
        secret_key="skey",
        region="ap-guangzhou",
        timeout_ms=5000,
        app_id="123456",
        streaming_enabled=True,
        ws_allow_http_fallback=False,
        ws_single_connection_enabled=True,
    )

    class _FakeWS:
        def __init__(self):
            self.closed = False
            self.turn_no = 0
            self.turn_recv_count = 0

        def send(self, payload):  # noqa: ANN001
            if isinstance(payload, (bytes, bytearray)):
                self.turn_no += 1
                self.turn_recv_count = 0

        def recv(self, timeout=None):  # noqa: ANN001
            _ = timeout
            self.turn_recv_count += 1
            if self.turn_recv_count == 1:
                text = "turn one" if self.turn_no <= 1 else "turn two"
                return {"result": {"voice_text_str": text}}
            if self.turn_recv_count == 2:
                raise TimeoutError()
            if self.turn_recv_count == 3:
                text = "turn one" if self.turn_no <= 1 else "turn two"
                return {"result": {"voice_text_str": text}}
            if self.turn_recv_count == 4:
                return {"final": 1}
            raise TimeoutError()

        def close(self):
            self.closed = True

    fake_ws = _FakeWS()

    def _fake_connect(*args, **kwargs):  # noqa: ANN002,ANN003
        _ = args, kwargs
        return fake_ws

    fake_client = types.ModuleType("websockets.sync.client")
    fake_client.connect = _fake_connect  # type: ignore[attr-defined]
    fake_sync = types.ModuleType("websockets.sync")
    fake_sync.client = fake_client  # type: ignore[attr-defined]
    fake_websockets = types.ModuleType("websockets")
    fake_websockets.sync = fake_sync  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "websockets", fake_websockets)
    monkeypatch.setitem(sys.modules, "websockets.sync", fake_sync)
    monkeypatch.setitem(sys.modules, "websockets.sync.client", fake_client)
    monkeypatch.setattr(provider, "_parse_ws_message", lambda x: x)

    first = provider.transcribe_stream(
        session_id="s-single",
        seq=1,
        text_hint="",
        audio_base64="UklGRg==",
        confidence=0.9,
        latency_ms=100,
        chunk_index=1,
        chunk_total=1,
        is_final=True,
    )
    second = provider.transcribe_stream(
        session_id="s-single",
        seq=2,
        text_hint="",
        audio_base64="UklGRg==",
        confidence=0.9,
        latency_ms=100,
        chunk_index=1,
        chunk_total=1,
        is_final=True,
    )
    assert first.transcript == "turn one"
    assert second.transcript == "turn two"
    assert len(provider._ws_contexts) == 1  # noqa: SLF001
    provider._close_ws_context("s-single")  # noqa: SLF001
    assert fake_ws.closed is True


def test_tencent_asr_duplex_should_reconnect_when_single_ws_closed(monkeypatch) -> None:
    provider = TencentASRProvider(
        secret_id="sid",
        secret_key="skey",
        region="ap-guangzhou",
        timeout_ms=5000,
        app_id="123456",
        streaming_enabled=True,
        ws_allow_http_fallback=False,
        ws_single_connection_enabled=True,
    )

    class _BrokenWS:
        def send(self, payload):  # noqa: ANN001
            _ = payload
            raise RuntimeError("ConnectionClosedError: no close frame received or sent")

        def recv(self, timeout=None):  # noqa: ANN001
            _ = timeout
            raise TimeoutError()

        def close(self):
            return None

    class _GoodWS:
        def __init__(self):
            self.recv_count = 0

        def send(self, payload):  # noqa: ANN001
            _ = payload

        def recv(self, timeout=None):  # noqa: ANN001
            _ = timeout
            self.recv_count += 1
            if self.recv_count == 1:
                return {"result": {"voice_text_str": "reconnect success"}}
            raise TimeoutError()

        def close(self):
            return None

    calls = {"n": 0}

    def _fake_connect(*args, **kwargs):  # noqa: ANN002,ANN003
        _ = args, kwargs
        calls["n"] += 1
        if calls["n"] == 1:
            return _BrokenWS()
        return _GoodWS()

    fake_client = types.ModuleType("websockets.sync.client")
    fake_client.connect = _fake_connect  # type: ignore[attr-defined]
    fake_sync = types.ModuleType("websockets.sync")
    fake_sync.client = fake_client  # type: ignore[attr-defined]
    fake_websockets = types.ModuleType("websockets")
    fake_websockets.sync = fake_sync  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "websockets", fake_websockets)
    monkeypatch.setitem(sys.modules, "websockets.sync", fake_sync)
    monkeypatch.setitem(sys.modules, "websockets.sync.client", fake_client)
    monkeypatch.setattr(provider, "_parse_ws_message", lambda x: x)

    result = provider.transcribe_stream(
        session_id="s-retry",
        seq=1,
        text_hint="",
        audio_base64="UklGRg==",
        confidence=0.9,
        latency_ms=120,
        chunk_index=1,
        chunk_total=1,
        is_final=True,
    )
    assert result.transcript == "reconnect success"
    assert calls["n"] == 2


def test_tencent_asr_duplex_should_use_partial_wait_window(monkeypatch) -> None:
    provider = TencentASRProvider(
        secret_id="sid",
        secret_key="skey",
        region="ap-guangzhou",
        timeout_ms=5000,
        app_id="123456",
        streaming_enabled=True,
        ws_allow_http_fallback=False,
        ws_partial_wait_ms=25,
    )

    class _FakeWS:
        def send(self, payload):  # noqa: ANN001
            _ = payload

        def recv(self, timeout=None):  # noqa: ANN001
            _ = timeout
            raise TimeoutError()

        def close(self):
            return None

    fake_ws = _FakeWS()
    calls: list[float] = []

    def _fake_connect(*args, **kwargs):  # noqa: ANN002,ANN003
        _ = args, kwargs
        return fake_ws

    original_collect = provider._collect_ws_messages  # noqa: SLF001

    def _collect_proxy(**kwargs):  # noqa: ANN003
        calls.append(float(kwargs.get("timeout_seconds") or 0))
        return original_collect(**kwargs)

    fake_client = types.ModuleType("websockets.sync.client")
    fake_client.connect = _fake_connect  # type: ignore[attr-defined]
    fake_sync = types.ModuleType("websockets.sync")
    fake_sync.client = fake_client  # type: ignore[attr-defined]
    fake_websockets = types.ModuleType("websockets")
    fake_websockets.sync = fake_sync  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "websockets", fake_websockets)
    monkeypatch.setitem(sys.modules, "websockets.sync", fake_sync)
    monkeypatch.setitem(sys.modules, "websockets.sync.client", fake_client)
    monkeypatch.setattr(provider, "_collect_ws_messages", _collect_proxy)
    monkeypatch.setattr(provider, "_parse_ws_message", lambda x: x)

    provider.transcribe_stream(
        session_id="s1",
        seq=9,
        text_hint="partial",
        audio_base64="UklGRg==",
        confidence=0.9,
        latency_ms=90,
        chunk_index=1,
        chunk_total=2,
        is_final=False,
    )
    provider._close_ws_context("s1:9")  # noqa: SLF001
    assert calls
    assert abs(calls[0] - 0.025) < 0.001


def test_tencent_asr_decode_stream_should_extract_pcm_from_wav_when_pcm_mode() -> None:
    provider = TencentASRProvider(
        secret_id="sid",
        secret_key="skey",
        region="ap-guangzhou",
        timeout_ms=5000,
        app_id="123456",
        streaming_enabled=True,
        voice_format=1,
    )
    pcm_payload = (b"\x01\x00\x02\x00") * 80
    buf = BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(pcm_payload)
    wav_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    decoded = provider._decode_audio_bytes_for_stream(wav_base64)  # noqa: SLF001
    assert decoded == pcm_payload


def test_tencent_asr_warmup_should_create_context(monkeypatch) -> None:
    provider = TencentASRProvider(
        secret_id="sid",
        secret_key="skey",
        region="ap-guangzhou",
        timeout_ms=5000,
        app_id="123456",
        streaming_enabled=True,
        prewarm_enabled=True,
    )

    class _FakeWS:
        def send(self, payload):  # noqa: ANN001
            _ = payload

        def recv(self, timeout=None):  # noqa: ANN001
            _ = timeout
            raise TimeoutError()

        def close(self):
            return None

    def _fake_connect(*args, **kwargs):  # noqa: ANN002,ANN003
        _ = args, kwargs
        return _FakeWS()

    fake_client = types.ModuleType("websockets.sync.client")
    fake_client.connect = _fake_connect  # type: ignore[attr-defined]
    fake_sync = types.ModuleType("websockets.sync")
    fake_sync.client = fake_client  # type: ignore[attr-defined]
    fake_websockets = types.ModuleType("websockets")
    fake_websockets.sync = fake_sync  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "websockets", fake_websockets)
    monkeypatch.setitem(sys.modules, "websockets.sync", fake_sync)
    monkeypatch.setitem(sys.modules, "websockets.sync.client", fake_client)

    provider.warmup(session_id="warmup-session")
    assert len(provider._ws_contexts) == 1  # noqa: SLF001
