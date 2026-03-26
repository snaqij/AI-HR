"""Realtime ASR smoke via client-side PCM chunk uploads.

This script exercises:
1) create/start AI interview session
2) auto upload PCM chunks to /rtc/asr/stream
3) verify events/turns write-back

Usage:
  python scripts/asr_pcm_stream_smoke.py --base-url http://127.0.0.1:8000 --wav-file ./sample.wav
"""

from __future__ import annotations

import argparse
import json
import math
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import wave
from pathlib import Path

from ai_hr.services.rtc.pcm_stream import build_asr_stream_payloads


def _request(method: str, url: str, payload: dict | None = None) -> tuple[int, dict]:
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url=url, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
            return int(resp.status), json.loads(body)
    except urllib.error.HTTPError as exc:
        raw = ""
        try:
            raw = exc.read().decode("utf-8")
        except Exception:
            raw = str(exc)
        try:
            return int(exc.code), json.loads(raw)
        except Exception:
            return int(exc.code), {"error": {"message": raw}}


def _create_seed(base_url: str, api_prefix: str) -> tuple[str, str, str]:
    status, job_resp = _request(
        "POST",
        f"{base_url}{api_prefix}/jobs",
        {
            "title": "Realtime ASR Smoke Engineer",
            "department": "Engineering",
            "city": "Shanghai",
            "salary_range": "30k-45k",
            "requirements": "Realtime ASR + Python",
        },
    )
    if status >= 300:
        raise RuntimeError(f"create_job_failed: {job_resp}")
    job_id = job_resp["data"]["id"]

    ext_id = f"asr-smoke-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    status, cand_resp = _request(
        "POST",
        f"{base_url}{api_prefix}/candidates/import",
        {
            "candidates": [
                {
                    "name": "Realtime ASR Candidate",
                    "source_channel": "self_hosted",
                    "external_candidate_id": ext_id,
                    "resume_text": "Python realtime streaming candidate profile",
                    "raw_profile": {"skills": ["Python", "ASR", "RTC"]},
                }
            ]
        },
    )
    if status >= 300:
        raise RuntimeError(f"create_candidate_failed: {cand_resp}")
    candidate_id = cand_resp["data"]["candidates"][0]["id"]

    status, sess_resp = _request(
        "POST",
        f"{base_url}{api_prefix}/ai/interviews/sessions",
        {"candidate_id": candidate_id, "job_id": job_id},
    )
    if status >= 300:
        raise RuntimeError(f"create_session_failed: {sess_resp}")
    session_id = sess_resp["data"]["session"]["id"]

    status, start_resp = _request(
        "POST",
        f"{base_url}{api_prefix}/ai/interviews/sessions/{session_id}/start",
        {"operator": "asr_smoke"},
    )
    if status >= 300:
        raise RuntimeError(f"start_session_failed: {start_resp}")
    return job_id, candidate_id, session_id


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Realtime ASR smoke by auto-calling /rtc/asr/stream")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-prefix", default="/api/v1")
    parser.add_argument("--wav-file", default="")
    parser.add_argument("--chunk-ms", type=int, default=400)
    parser.add_argument("--seq", type=int, default=1)
    args = parser.parse_args()

    _, _, session_id = _create_seed(args.base_url, args.api_prefix)

    if args.wav_file:
        pcm_bytes, sample_rate, channels = _load_wav_pcm(args.wav_file)
    else:
        pcm_bytes, sample_rate, channels = _gen_sine_pcm()

    payloads = build_asr_stream_payloads(
        seq=args.seq,
        pcm_bytes=pcm_bytes,
        sample_rate=sample_rate,
        channels=channels,
        chunk_ms=max(100, args.chunk_ms),
        text_hint="realtime pcm upload smoke",
        target_latency_ms=700,
    )

    stream_results: list[dict] = []
    for payload in payloads:
        status, resp = _request(
            "POST",
            f"{args.base_url}{args.api_prefix}/ai/interviews/sessions/{session_id}/rtc/asr/stream",
            payload,
        )
        if status >= 300:
            raise RuntimeError(f"asr_stream_failed: status={status}, resp={resp}")
        stream_results.append(resp["data"])

    query = urllib.parse.urlencode(
        {
            "session_id": session_id,
            "event_type": "ai_interview.rtc.asr",
            "limit": 200,
        }
    )
    status, audit_resp = _request("GET", f"{args.base_url}{args.api_prefix}/audit/events?{query}")
    if status >= 300:
        raise RuntimeError(f"audit_query_failed: {audit_resp}")

    status, replay_resp = _request("GET", f"{args.base_url}{args.api_prefix}/ai/interviews/sessions/{session_id}/replay?limit=200")
    if status >= 300:
        raise RuntimeError(f"replay_query_failed: {replay_resp}")

    audit_items = audit_resp.get("data", {}).get("items", [])
    replay_items = replay_resp.get("data", {}).get("items", [])
    providers = [str(item.get("payload", {}).get("provider", "")) for item in audit_items]
    provider_set = sorted({item for item in providers if item})

    summary = {
        "session_id": session_id,
        "chunks_uploaded": len(payloads),
        "asr_stream_ok": len(stream_results),
        "audit_event_count": len(audit_items),
        "replay_turn_count": len(replay_items),
        "candidate_turn_count": len([item for item in replay_items if item.get("speaker") in {"candidate", "candidate_partial"}]),
        "providers_seen": provider_set,
        "latency_samples_ms": [item.get("latency_ms") for item in stream_results],
        "all_realtime_target_met": all(bool(item.get("realtime_target_met")) for item in stream_results),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
