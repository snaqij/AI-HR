from __future__ import annotations

from fastapi.testclient import TestClient
from ai_hr.main import app

client = TestClient(app)


def test_provider_health_endpoint_should_return_all_domains() -> None:
    resp = client.get("/health/providers")
    assert resp.status_code == 200
    payload = resp.json()["data"]
    assert set(payload.keys()) == {"rtc", "llm", "asr", "tts"}
    assert payload["rtc"]["provider"] in {"mock", "livekit"}
    assert "circuit" in payload["rtc"]
