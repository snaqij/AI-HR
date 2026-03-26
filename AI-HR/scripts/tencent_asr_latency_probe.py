from __future__ import annotations

import argparse
import base64
import json
import math
import os
import struct
import time
import wave
from io import BytesIO

from ai_hr.core.config import get_settings
from ai_hr.services.speech.tencent_providers import TencentASRProvider


def percentile(values: list[int], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, min(len(ordered), int(len(ordered) * p + 0.9999)))
    return float(ordered[rank - 1])


def stats(values: list[int]) -> dict:
    return {
        "p50": percentile(values, 0.50),
        "p95": percentile(values, 0.95),
        "p99": percentile(values, 0.99),
        "avg": round(sum(values) / len(values), 2) if values else 0.0,
        "samples": len(values),
    }


def build_wav_base64(*, sample_rate: int, duration_ms: int, freq_hz: float = 440.0) -> str:
    frame_count = max(1, int(sample_rate * duration_ms / 1000))
    amp = 12000
    pcm = bytearray()
    for i in range(frame_count):
        v = int(amp * math.sin(2 * math.pi * freq_hz * (i / sample_rate)))
        pcm.extend(struct.pack("<h", v))
    buf = BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(bytes(pcm))
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe Tencent ASR latency directly.")
    parser.add_argument("--rounds", type=int, default=8, help="How many turns to run")
    parser.add_argument("--partial-chunks", type=int, default=4, help="Chunks per turn; last chunk is final")
    parser.add_argument("--frame-ms", type=int, default=30, help="Audio duration per chunk")
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--sleep-ms", type=int, default=50, help="Sleep between turns")
    parser.add_argument("--single-connection", action="store_true", help="Use session-level single WS connection")
    parser.add_argument("--force-http", action="store_true", help="Disable WS and force HTTP mode")
    parser.add_argument("--session-id", default=f"probe-{int(time.time())}")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()

    if not settings.tencent_secret_id or not settings.tencent_secret_key:
        raise RuntimeError("Missing Tencent credentials: AI_HR_TENCENT_SECRET_ID / AI_HR_TENCENT_SECRET_KEY")

    provider = TencentASRProvider(
        secret_id=settings.tencent_secret_id,
        secret_key=settings.tencent_secret_key,
        region=settings.tencent_region,
        timeout_ms=settings.asr_stream_timeout_ms,
        engine_type=settings.asr_tencent_engine_type,
        voice_format=settings.asr_tencent_voice_format,
        endpoint=settings.asr_base_url or "https://asr.tencentcloudapi.com",
        app_id=None if args.force_http else settings.asr_tencent_app_id,
        ws_base_url=settings.asr_tencent_ws_base_url,
        streaming_enabled=(not args.force_http) and settings.asr_tencent_streaming_enabled,
        ws_allow_http_fallback=settings.asr_tencent_ws_allow_http_fallback,
        ws_expire_seconds=settings.asr_tencent_ws_expire_seconds,
        ws_session_ttl_seconds=settings.asr_tencent_ws_session_ttl_seconds,
        ws_partial_wait_ms=settings.asr_tencent_ws_partial_wait_ms,
        ws_single_connection_enabled=args.single_connection,
    )

    audio_base64 = build_wav_base64(sample_rate=args.sample_rate, duration_ms=args.frame_ms)

    partial_provider_ms: list[int] = []
    partial_wall_ms: list[int] = []
    final_provider_ms: list[int] = []
    final_wall_ms: list[int] = []
    providers: dict[str, int] = {}

    rounds = max(1, args.rounds)
    chunk_total = max(1, args.partial_chunks)
    for seq in range(1, rounds + 1):
        for chunk_index in range(1, chunk_total + 1):
            is_final = chunk_index >= chunk_total
            start = time.perf_counter()
            result = provider.transcribe_stream(
                session_id=args.session_id,
                seq=seq,
                text_hint="",
                audio_base64=audio_base64,
                confidence=0.9,
                latency_ms=120 if not is_final else 320,
                chunk_index=chunk_index,
                chunk_total=chunk_total,
                is_final=is_final,
            )
            wall_ms = max(1, int((time.perf_counter() - start) * 1000))
            providers[result.provider] = providers.get(result.provider, 0) + 1
            if is_final:
                final_provider_ms.append(int(result.latency_ms))
                final_wall_ms.append(wall_ms)
            else:
                partial_provider_ms.append(int(result.latency_ms))
                partial_wall_ms.append(wall_ms)
        if args.sleep_ms > 0:
            time.sleep(args.sleep_ms / 1000)

    output = {
        "config": {
            "rounds": rounds,
            "partial_chunks": chunk_total,
            "frame_ms": args.frame_ms,
            "sample_rate": args.sample_rate,
            "single_connection": args.single_connection,
            "force_http": args.force_http,
            "session_id": args.session_id,
            "env": os.getenv("AI_HR_ENV", "dev"),
        },
        "provider_usage": providers,
        "partial_provider_latency_ms": stats(partial_provider_ms),
        "partial_wall_latency_ms": stats(partial_wall_ms),
        "final_provider_latency_ms": stats(final_provider_ms),
        "final_wall_latency_ms": stats(final_wall_ms),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

