from __future__ import annotations

import base64
import json

from scripts.rtc_asr_ingest_ws_smoke import _build_livekit_webhook_token, _to_ingest_ws_url


def _decode_payload(token: str) -> dict:
    payload_b64 = token.split(".")[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(payload_b64.encode("utf-8")).decode("utf-8"))


def test_to_ingest_ws_url_should_map_http_and_api_prefix() -> None:
    assert (
        _to_ingest_ws_url("http://127.0.0.1:8000", "/api/v1")
        == "ws://127.0.0.1:8000/api/v1/ai/interviews/rtc/asr/ingest/ws"
    )
    assert (
        _to_ingest_ws_url("https://hr.example.com/api/v1", "/api/v1")
        == "wss://hr.example.com/api/v1/ai/interviews/rtc/asr/ingest/ws"
    )


def test_build_livekit_webhook_token_should_include_issuer_claim() -> None:
    token = _build_livekit_webhook_token(api_key="livekit-key", api_secret="livekit-secret")
    assert len(token.split(".")) == 3
    payload = _decode_payload(token)
    assert payload["iss"] == "livekit-key"
    assert int(payload["exp"]) > int(payload["nbf"])
