from __future__ import annotations

import base64
import json
from typing import Any

import pytest

from ai_hr.core.config import Settings
from ai_hr.core.exceptions import ConnectorOperationError
from ai_hr.services.speech.factory import create_asr_provider, create_tts_provider


def test_mock_asr_provider_should_return_text_hint() -> None:
    settings = Settings(asr_provider="mock")
    provider = create_asr_provider(settings)
    result = provider.transcribe_stream(
        session_id="s1",
        seq=1,
        text_hint="candidate answer",
        audio_base64=None,
        confidence=0.88,
        latency_ms=620,
    )
    assert result.transcript == "candidate answer"
    assert result.provider == "mock"


def test_mock_tts_provider_should_return_chunks_and_mock_uris() -> None:
    settings = Settings(tts_provider="mock")
    provider = create_tts_provider(settings)
    result = provider.synthesize_stream(
        session_id="s1",
        text="请介绍一下你的项目经验",
        voice="default",
        chunk_size=6,
    )
    assert len(result.chunks) >= 1
    assert result.audio_uris[0].startswith("mock://tts/")
    assert result.provider == "mock"


class _FakeHTTPResponse:
    def __init__(self, payload: dict[str, Any]):
        self._raw = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self._raw


def test_tencent_asr_provider_should_call_tc3_and_parse_result(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def _fake_urlopen(request, timeout=None):  # noqa: ANN001
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = request.data.decode("utf-8")
        return _FakeHTTPResponse({"Response": {"Result": "腾讯云转写结果"}})

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    settings = Settings(
        asr_provider="tencent",
        tencent_secret_id="id_demo",
        tencent_secret_key="key_demo",
        tencent_region="ap-shanghai",
    )
    provider = create_asr_provider(settings)
    audio_base64 = base64.b64encode(b"wav-bytes").decode("utf-8")
    result = provider.transcribe_stream(
        session_id="s-tc-1",
        seq=2,
        text_hint="hint",
        audio_base64=audio_base64,
        confidence=0.9,
        latency_ms=420,
    )
    assert result.transcript == "腾讯云转写结果"
    assert result.provider == "tencent"
    assert captured["url"].startswith("https://asr.tencentcloudapi.com/")
    assert "TC3-HMAC-SHA256" in captured["headers"]["Authorization"]
    lower_headers = {str(k).lower(): v for k, v in captured["headers"].items()}
    assert lower_headers["x-tc-action"] == "SentenceRecognition"
    body_payload = json.loads(captured["body"])
    assert body_payload["VoiceFormat"] == "wav"


def test_tencent_tts_provider_should_call_tc3_and_parse_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def _fake_urlopen(request, timeout=None):  # noqa: ANN001
        calls.append(
            {
                "url": request.full_url,
                "headers": dict(request.header_items()),
                "body": request.data.decode("utf-8"),
            }
        )
        return _FakeHTTPResponse({"Response": {"Audio": base64.b64encode(b"mp3-bytes").decode("utf-8")}})

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    settings = Settings(
        tts_provider="tencent",
        tencent_secret_id="id_demo",
        tencent_secret_key="key_demo",
        tencent_region="ap-shanghai",
    )
    provider = create_tts_provider(settings)
    result = provider.synthesize_stream(
        session_id="s-tc-2",
        text="hello world",
        voice="default",
        chunk_size=5,
    )
    assert result.provider == "tencent"
    assert len(result.chunks) == 2
    assert len(calls) == 2
    assert result.audio_uris[0].startswith("data:audio/mpeg;base64,")
    assert calls[0]["url"].startswith("https://tts.tencentcloudapi.com/")
    assert "TC3-HMAC-SHA256" in calls[0]["headers"]["Authorization"]
    lower_headers = {str(k).lower(): v for k, v in calls[0]["headers"].items()}
    assert lower_headers["x-tc-action"] == "TextToVoice"


def test_tencent_tts_provider_should_merge_short_tail_chunk(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_urlopen(request, timeout=None):  # noqa: ANN001
        return _FakeHTTPResponse({"Response": {"Audio": base64.b64encode(b"ok").decode("utf-8")}})

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    settings = Settings(
        tts_provider="tencent",
        tencent_secret_id="id_demo",
        tencent_secret_key="key_demo",
        tencent_region="ap-shanghai",
    )
    provider = create_tts_provider(settings)
    result = provider.synthesize_stream(
        session_id="s-tc-tail",
        text="请介绍一下你最近做过的项目复杂度。",
        voice="default",
        chunk_size=10,
    )
    assert result.provider == "tencent"
    assert all(len(item.strip()) > 0 for item in result.chunks)
    assert all(len(item) > 3 for item in result.chunks)


def test_tencent_asr_provider_should_raise_on_business_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_urlopen(request, timeout=None):  # noqa: ANN001
        return _FakeHTTPResponse(
            {
                "Response": {
                    "Error": {"Code": "InvalidParameter", "Message": "voice format invalid"},
                    "RequestId": "rid-demo",
                }
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    settings = Settings(
        asr_provider="tencent",
        tencent_secret_id="id_demo",
        tencent_secret_key="key_demo",
        tencent_region="ap-shanghai",
    )
    provider = create_asr_provider(settings)
    with pytest.raises(ConnectorOperationError, match="Tencent ASR business error"):
        provider.transcribe_stream(
            session_id="s-tc-err",
            seq=1,
            text_hint="hint",
            audio_base64=base64.b64encode(b"wav-bytes").decode("utf-8"),
            confidence=0.9,
            latency_ms=300,
        )
