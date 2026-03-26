"""RTC room ASR ingest websocket smoke tool.

This script validates low-latency room-level ingest:
1) optional webhook preflight (participant_joined / track_published)
2) websocket connection to /ai/interviews/rtc/asr/ingest/ws
3) continuous audio_frame streaming with ack/result validation

Usage:
  uv run --project AI-HR python AI-HR/scripts/rtc_asr_ingest_ws_smoke.py \
    --base-url http://127.0.0.1:8000 --api-prefix /api/v1 --room-id <room_id> --wav-file sample.wav
"""

from __future__ import annotations

import argparse
import base64
import hmac
import json
import math
import struct
import time
import urllib.error
import urllib.request
import wave
from hashlib import sha256
from io import BytesIO
from urllib.parse import urlparse

from ai_hr.services.rtc.pcm_stream import build_asr_stream_payloads


def _request_json(
    *,
    method: str,
    url: str,
    payload: dict | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict]:
    body = json.dumps(payload or {}).encode("utf-8") if payload is not None else None
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url=url, method=method, data=body, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return int(resp.status), json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        try:
            return int(exc.code), json.loads(raw)
        except Exception:
            return int(exc.code), {"error": {"message": raw or str(exc)}}


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def _build_livekit_webhook_token(*, api_key: str, api_secret: str) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"iss": api_key, "nbf": now - 5, "exp": now + 180}
    h = _b64url(json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    p = _b64url(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    sign = hmac.new(api_secret.encode("utf-8"), f"{h}.{p}".encode("utf-8"), sha256).digest()
    return f"{h}.{p}.{_b64url(sign)}"


def _to_ingest_ws_url(base_url: str, api_prefix: str) -> str:
    parsed = urlparse(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    base_path = parsed.path.rstrip("/")
    if base_path.endswith(api_prefix.rstrip("/")):
        path = f"{base_path}/ai/interviews/rtc/asr/ingest/ws"
    else:
        path = f"{base_path}{api_prefix}/ai/interviews/rtc/asr/ingest/ws"
    return f"{scheme}://{parsed.netloc}{path}"


def _load_wav_pcm(wav_path: str) -> tuple[bytes, int, int]:
    with wave.open(wav_path, "rb") as wf:
        channels = wf.getnchannels()
        sample_rate = wf.getframerate()
        sample_width = wf.getsampwidth()
        if sample_width != 2:
            raise RuntimeError(f"wav sample width must be 16-bit, got {sample_width * 8}-bit")
        pcm = wf.readframes(wf.getnframes())
    return pcm, sample_rate, channels


def _gen_sine_pcm(*, seconds: float = 2.0, sample_rate: int = 16000, freq_hz: float = 440.0) -> tuple[bytes, int, int]:
    total = max(1, int(sample_rate * seconds))
    out = bytearray()
    for i in range(total):
        amp = int(0.2 * 32767 * math.sin(2 * math.pi * freq_hz * (i / sample_rate)))
        out.extend(struct.pack("<h", amp))
    return bytes(out), sample_rate, 1


def _simulate_webhook_preflight(
    *,
    base_url: str,
    api_prefix: str,
    room_id: str,
    participant_identity: str,
    track_sid: str,
    webhook_api_key: str | None,
    webhook_api_secret: str | None,
) -> dict:
    headers: dict[str, str] = {}
    if webhook_api_key and webhook_api_secret:
        token = _build_livekit_webhook_token(api_key=webhook_api_key, api_secret=webhook_api_secret)
        headers["Authorization"] = f"Bearer {token}"
    endpoint = f"{base_url.rstrip('/')}{api_prefix.rstrip('/')}/ai/interviews/rtc/webhooks/livekit"
    joined_status, joined_resp = _request_json(
        method="POST",
        url=endpoint,
        payload={
            "id": f"smoke-join-{int(time.time() * 1000)}",
            "event": "participant_joined",
            "room": {"name": room_id},
            "participant": {"identity": participant_identity},
        },
        headers=headers,
    )
    track_status, track_resp = _request_json(
        method="POST",
        url=endpoint,
        payload={
            "id": f"smoke-track-{int(time.time() * 1000)}",
            "event": "track_published",
            "room": {"name": room_id},
            "participant": {"identity": participant_identity},
            "track": {"sid": track_sid, "type": "audio"},
        },
        headers=headers,
    )
    return {
        "join_status": joined_status,
        "join_ok": bool((joined_resp.get("data") or {}).get("accepted")),
        "track_status": track_status,
        "track_ok": bool((track_resp.get("data") or {}).get("accepted")),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="RTC room ASR ingest websocket smoke")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-prefix", default="/api/v1")
    parser.add_argument("--room-id", required=True)
    parser.add_argument("--seq", type=int, default=1)
    parser.add_argument("--chunk-ms", type=int, default=200)
    parser.add_argument("--wav-file", default="")
    parser.add_argument("--text-hint", default="room ingest websocket smoke")
    parser.add_argument("--target-latency-ms", type=int, default=700)
    parser.add_argument("--participant-identity", default="candidate-smoke:web")
    parser.add_argument("--track-sid", default="TR_SMOKE_AUDIO_1")
    parser.add_argument("--sleep-ms", type=int, default=30)
    parser.add_argument("--api-key", default="")
    parser.add_argument("--simulate-webhook", action="store_true")
    parser.add_argument("--webhook-api-key", default="")
    parser.add_argument("--webhook-api-secret", default="")
    args = parser.parse_args()

    if args.wav_file:
        pcm_bytes, sample_rate, channels = _load_wav_pcm(args.wav_file)
    else:
        pcm_bytes, sample_rate, channels = _gen_sine_pcm()

    payloads = build_asr_stream_payloads(
        seq=max(1, int(args.seq)),
        pcm_bytes=pcm_bytes,
        sample_rate=sample_rate,
        channels=channels,
        chunk_ms=max(100, int(args.chunk_ms)),
        text_hint=str(args.text_hint or ""),
        target_latency_ms=max(100, int(args.target_latency_ms)),
        input_format="wav",
    )
    for idx, payload in enumerate(payloads, start=1):
        payload["room_id"] = args.room_id
        payload["frame_id"] = f"room-ingest-{args.seq}-{idx}"
        payload["participant_identity"] = args.participant_identity
        payload["track_sid"] = args.track_sid
        payload["auto_followup"] = True
        payload["auto_tts_publish"] = True

    preflight = None
    if args.simulate_webhook:
        preflight = _simulate_webhook_preflight(
            base_url=args.base_url,
            api_prefix=args.api_prefix,
            room_id=args.room_id,
            participant_identity=args.participant_identity,
            track_sid=args.track_sid,
            webhook_api_key=(args.webhook_api_key or "").strip() or None,
            webhook_api_secret=(args.webhook_api_secret or "").strip() or None,
        )

    ws_url = _to_ingest_ws_url(args.base_url, args.api_prefix)
    ws_headers = {}
    if (args.api_key or "").strip():
        ws_headers["x-api-key"] = args.api_key.strip()

    try:
        from websockets.sync.client import connect as ws_connect
    except Exception as exc:
        raise RuntimeError("websockets package is required (pip/uv install websockets)") from exc

    ack_latencies: list[int] = []
    asr_latencies: list[int] = []
    tts_latencies: list[int] = []
    success_count = 0
    published_count = 0
    with ws_connect(ws_url, additional_headers=ws_headers, open_timeout=10, close_timeout=2, max_size=8 * 1024 * 1024) as ws:
        connected = json.loads(ws.recv(timeout=10))
        if str(connected.get("type")) != "ingest.connected":
            raise RuntimeError(f"unexpected ws hello: {connected}")
        for payload in payloads:
            started = time.perf_counter()
            ws.send(json.dumps({"type": "audio_frame", "payload": payload}, ensure_ascii=False))
            ack = json.loads(ws.recv(timeout=15))
            if str(ack.get("type")) != "ingest.ack":
                raise RuntimeError(f"unexpected ack payload: {ack}")
            if str(ack.get("status")) not in {"accepted", "duplicate"}:
                raise RuntimeError(f"ingest ack status invalid: {ack}")
            ack_latencies.append(int(ack.get("ack_latency_ms") or 0))
            if str(ack.get("status")) == "duplicate":
                continue

            result_msg = json.loads(ws.recv(timeout=25))
            if str(result_msg.get("type")) != "ingest.result":
                raise RuntimeError(f"unexpected ingest result payload: {result_msg}")
            data = result_msg.get("data") or {}
            asr_data = data.get("asr") or {}
            tts_data = data.get("tts") or {}
            asr_latencies.append(int(asr_data.get("latency_ms") or 0))
            tts_latencies.append(int((tts_data.get("latency_breakdown") or {}).get("e2e_ms") or 0))
            published_count += int(bool(tts_data.get("published")))
            success_count += 1
            elapsed = max(1, int((time.perf_counter() - started) * 1000))
            print(
                json.dumps(
                    {
                        "type": "turn_result",
                        "frame_id": payload["frame_id"],
                        "seq": payload["seq"],
                        "asr_ms": asr_latencies[-1],
                        "tts_ms": tts_latencies[-1],
                        "e2e_ms": elapsed,
                        "published": bool(tts_data.get("published")),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            if args.sleep_ms > 0:
                time.sleep(args.sleep_ms / 1000)

    summary = {
        "ws_url": ws_url,
        "room_id": args.room_id,
        "payload_count": len(payloads),
        "success_count": success_count,
        "tts_published_count": published_count,
        "ack_latency_ms": ack_latencies,
        "asr_latency_ms": asr_latencies,
        "tts_latency_ms": tts_latencies,
        "preflight": preflight,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
