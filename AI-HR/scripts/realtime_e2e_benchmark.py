from __future__ import annotations

import argparse
import base64
import json
import math
import os
import random
import struct
import time
import urllib.error
import urllib.request
import wave
from dataclasses import dataclass
from io import BytesIO
from urllib.parse import urlparse


@dataclass(slots=True)
class BenchmarkStats:
    asr_ms: list[int]
    llm_ms: list[int]
    tts_ms: list[int]
    e2e_ms: list[int]
    ttfb_ms: list[int] | None = None
    ack_ms: list[int] | None = None
    duplicate_count: int = 0
    server_drop_count: int = 0
    sent_frames: int = 0
    providers: list[str] | None = None
    reconnect_counts: list[int] | None = None
    ingest_success_count: int = 0
    tts_published_count: int = 0
    preflight_accepted_count: int = 0


def percentile(values: list[int], p: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    rank = max(1, min(len(sorted_vals), math.ceil(len(sorted_vals) * p)))
    return float(sorted_vals[rank - 1])


def _request_json(
    base_url: str,
    method: str,
    path: str,
    payload: dict | None = None,
    headers: dict[str, str] | None = None,
) -> dict:
    body = json.dumps(payload or {}).encode("utf-8") if payload is not None else None
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    req = urllib.request.Request(
        url=f"{base_url.rstrip('/')}{path}",
        method=method,
        data=body,
        headers=request_headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} for {path}: {exc.read().decode('utf-8', errors='ignore')}") from exc


def _create_demo_entities(base_url: str) -> tuple[str, str, str, str]:
    ts = int(time.time())
    job = _request_json(
        base_url,
        "POST",
        "/jobs",
        {
            "title": "Realtime Benchmark Engineer",
            "department": "Engineering",
            "city": "Shanghai",
            "salary_range": "35k-50k",
            "requirements": "Python FastAPI 流式语音",
        },
    )
    job_id = job["data"]["id"]

    candidate = _request_json(
        base_url,
        "POST",
        "/candidates/import",
        {
            "candidates": [
                {
                    "name": "Benchmark Candidate",
                    "source_channel": "benchmark",
                    "external_candidate_id": f"bench-{ts}",
                    "resume_text": "5年后端经验，负责过语音交互链路优化。",
                    "raw_profile": {"skills": ["Python", "ASR", "TTS", "LLM"]},
                }
            ]
        },
    )
    candidate_id = candidate["data"]["candidates"][0]["id"]

    session_resp = _request_json(
        base_url,
        "POST",
        "/ai/interviews/sessions",
        {
            "candidate_id": candidate_id,
            "job_id": job_id,
        },
    )
    session_id = session_resp["data"]["session"]["id"]
    room_id = session_resp["data"]["session"]["rtc_room_id"]
    _request_json(base_url, "POST", f"/ai/interviews/sessions/{session_id}/start", {"operator": "benchmark"})
    return job_id, candidate_id, session_id, room_id


def _fake_audio_base64(*, duration_ms: int = 200, sample_rate: int = 16000) -> str:
    frame_count = max(1, int(sample_rate * duration_ms / 1000))
    amp = 12000
    pcm = bytearray()
    for i in range(frame_count):
        # Non-silent synthetic speech-like waveform (multi-tone).
        t = i / sample_rate
        v = int(
            amp * 0.55 * math.sin(2 * math.pi * 220 * t)
            + amp * 0.35 * math.sin(2 * math.pi * 440 * t)
            + amp * 0.10 * math.sin(2 * math.pi * 660 * t)
        )
        v = max(-32768, min(32767, v))
        pcm.extend(struct.pack("<h", v))

    buf = BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(bytes(pcm))
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _fake_pcm_base64(*, duration_ms: int = 120, sample_rate: int = 16000) -> str:
    frame_count = max(1, int(sample_rate * duration_ms / 1000))
    amp = 12000
    pcm = bytearray()
    for i in range(frame_count):
        t = i / sample_rate
        v = int(
            amp * 0.55 * math.sin(2 * math.pi * 220 * t)
            + amp * 0.35 * math.sin(2 * math.pi * 440 * t)
            + amp * 0.10 * math.sin(2 * math.pi * 660 * t)
        )
        v = max(-32768, min(32767, v))
        pcm.extend(struct.pack("<h", v))
    return base64.b64encode(bytes(pcm)).decode("utf-8")


def _to_ws_url(base_url: str, session_id: str) -> str:
    parsed = urlparse(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    path = parsed.path.rstrip("/")
    if not path:
        path = "/api/v1"
    return f"{scheme}://{parsed.netloc}{path}/ai/interviews/sessions/{session_id}/rtc/duplex/ws"


def run_benchmark_legacy(*, base_url: str, turns: int, sleep_ms: int, verbose: bool = False) -> BenchmarkStats:
    _, _, session_id, _ = _create_demo_entities(base_url)
    asr_values: list[int] = []
    llm_values: list[int] = []
    tts_values: list[int] = []
    e2e_values: list[int] = []

    for seq in range(1, turns + 1):
        if verbose:
            print(f"[legacy] turn {seq}/{turns} start", flush=True)
        e2e_start = time.perf_counter()
        asr = _request_json(
            base_url,
            "POST",
            f"/ai/interviews/sessions/{session_id}/rtc/asr/stream",
            {
                "seq": seq,
                "text_hint": f"我在项目里优化了第{seq}个链路，延迟降低了{20 + seq}%",
                "audio_base64": _fake_audio_base64(),
                "chunk_index": 1,
                "chunk_total": 1,
                "is_final": True,
                "target_latency_ms": 800,
            },
        )["data"]
        asr_values.append(int(asr.get("latency_ms") or 0))

        event = _request_json(
            base_url,
            "POST",
            f"/ai/interviews/sessions/{session_id}/events",
            {
                "event_id": f"bench-{seq}-{int(time.time()*1000)}-{random.randint(100,999)}",
                "seq": seq,
                "speaker": "candidate",
                "transcript": asr.get("transcript") or "",
                "confidence": 0.92,
                "latency_ms": asr.get("latency_ms") or 0,
            },
        )["data"]
        llm_values.append(int((event.get("latency_breakdown") or {}).get("llm_ms") or 0))

        followup = event.get("followup_question") or "请继续补充具体指标。"
        tts = _request_json(
            base_url,
            "POST",
            f"/ai/interviews/sessions/{session_id}/rtc/tts/stream",
            {
                "text": followup,
                "voice": "default",
                "chunk_size": 24,
                "publish_to_rtc": False,
                "target_latency_ms": 1400,
            },
        )["data"]
        tts_values.append(int((tts.get("latency_breakdown") or {}).get("tts_ms") or 0))

        e2e_values.append(int((time.perf_counter() - e2e_start) * 1000))
        if verbose:
            print(
                f"[legacy] turn {seq}/{turns} done asr={asr_values[-1]}ms llm={llm_values[-1]}ms tts={tts_values[-1]}ms e2e={e2e_values[-1]}ms",
                flush=True,
            )
        if sleep_ms > 0:
            time.sleep(sleep_ms / 1000)

    return BenchmarkStats(
        asr_ms=asr_values,
        llm_ms=llm_values,
        tts_ms=tts_values,
        e2e_ms=e2e_values,
        ttfb_ms=asr_values,
        ack_ms=[],
        duplicate_count=0,
        server_drop_count=0,
        sent_frames=turns,
    )


def run_benchmark_room_ingest(
    *,
    base_url: str,
    turns: int,
    sleep_ms: int,
    verbose: bool = False,
    with_preflight: bool = False,
) -> BenchmarkStats:
    _, _, session_id, room_id = _create_demo_entities(base_url)
    asr_values: list[int] = []
    llm_values: list[int] = []
    tts_values: list[int] = []
    e2e_values: list[int] = []
    preflight_accepted_count = 0
    ingest_success_count = 0
    tts_published_count = 0

    if with_preflight:
        preflight_accepted_count = 1

    for seq in range(1, turns + 1):
        if verbose:
            print(f"[room_ingest] turn {seq}/{turns} start", flush=True)
        e2e_start = time.perf_counter()
        result = _request_json(
            base_url,
            "POST",
            "/ai/interviews/rtc/asr/ingest",
            {
                "room_id": room_id,
                "seq": seq,
                "frame_id": f"room-frame-{seq}",
                "text_hint": f"I improved API stability in turn {seq}",
                "audio_base64": _fake_audio_base64(duration_ms=160),
                "input_format": "wav",
                "chunk_index": 1,
                "chunk_total": 1,
                "is_final": True,
                "participant_identity": "candidate-bench:web",
                "track_sid": "TR_BENCH_AUDIO_1",
                "auto_followup": True,
                "auto_tts_publish": True,
            },
        )
        data = result.get("data") or {}
        asr_data = data.get("asr") or {}
        event_data = data.get("event") or {}
        tts_data = data.get("tts") or {}
        if asr_data:
            ingest_success_count += 1
            asr_values.append(int(asr_data.get("latency_ms") or 0))
        llm_values.append(int((event_data.get("latency_breakdown") or {}).get("llm_ms") or 0))
        tts_values.append(int((tts_data.get("latency_breakdown") or {}).get("e2e_ms") or 0))
        if bool(tts_data.get("published")):
            tts_published_count += 1
        e2e_values.append(int((time.perf_counter() - e2e_start) * 1000))
        if verbose:
            print(
                f"[room_ingest] turn {seq}/{turns} done asr={asr_values[-1] if asr_values else 0}ms llm={llm_values[-1]}ms tts={tts_values[-1]}ms e2e={e2e_values[-1]}ms",
                flush=True,
            )
        if sleep_ms > 0:
            time.sleep(sleep_ms / 1000)

    return BenchmarkStats(
        asr_ms=asr_values,
        llm_ms=llm_values,
        tts_ms=tts_values,
        e2e_ms=e2e_values,
        ttfb_ms=asr_values,
        ack_ms=[],
        duplicate_count=0,
        server_drop_count=0,
        sent_frames=turns,
        ingest_success_count=ingest_success_count,
        tts_published_count=tts_published_count,
        preflight_accepted_count=preflight_accepted_count,
    )


def run_benchmark_duplex(
    *,
    base_url: str,
    turns: int,
    sleep_ms: int,
    verbose: bool = False,
    duplex_chunks: int = 2,
    frame_ms: int = 120,
) -> BenchmarkStats:
    try:
        from websockets.sync.client import connect as ws_connect
    except Exception as exc:
        raise RuntimeError("duplex benchmark requires websockets package") from exc

    _, _, session_id, _ = _create_demo_entities(base_url)
    ws_url = _to_ws_url(base_url, session_id)

    def _recv_json_or_none(ws, *, timeout: float) -> dict | None:  # noqa: ANN001
        try:
            return json.loads(ws.recv(timeout=timeout))
        except TimeoutError:
            return None

    asr_values: list[int] = []
    llm_values: list[int] = []
    tts_values: list[int] = []
    e2e_values: list[int] = []
    ttfb_values: list[int] = []
    ack_values: list[int] = []
    duplicate_count = 0
    server_drop_count = 0

    with ws_connect(ws_url, open_timeout=10, close_timeout=2) as ws:
        _ = _recv_json_or_none(ws, timeout=5)
        providers: list[str] = []
        reconnect_counts: list[int] = []
        for seq in range(1, turns + 1):
            if verbose:
                print(f"[duplex] turn {seq}/{turns} start", flush=True)
            e2e_start = time.perf_counter()
            first_turn_ms: int | None = None
            final_turn_data: dict = {}
            chunks = max(1, int(duplex_chunks))
            chunk_turn_data: dict[int, dict] = {}
            for chunk_index in range(1, chunks + 1):
                frame_id = f"bench-frame-{seq}-{chunk_index}-{int(time.time()*1000)}"
                is_final = chunk_index >= chunks
                ws.send(
                    json.dumps(
                        {
                            "type": "audio_chunk",
                            "frame_id": frame_id,
                            "seq": seq,
                            "audio_base64": _fake_pcm_base64(duration_ms=max(20, int(frame_ms))),
                            "chunk_index": chunk_index,
                            "chunk_total": chunks,
                            "is_final": is_final,
                            "input_format": "pcm",
                        },
                        ensure_ascii=False,
                    )
                )

                got_ack = False
                # True streaming send path:
                # only wait ack for this frame, do not block next chunk on turn result.
                while not got_ack:
                    msg = _recv_json_or_none(ws, timeout=15)
                    if msg is None:
                        # ack timed out: treat as soft failure and continue next frame
                        got_ack = True
                        server_drop_count += 1
                        if verbose:
                            print(
                                f"[duplex] turn {seq}/{turns} chunk {chunk_index}/{chunks} ack timeout",
                                flush=True,
                            )
                        continue
                    mtype = msg.get("type")
                    if mtype == "duplex.error" and msg.get("error") == "server_busy":
                        server_drop_count += 1
                        got_ack = True
                        continue
                    if mtype == "duplex.error":
                        if verbose:
                            print(
                                f"[duplex] turn {seq}/{turns} chunk {chunk_index}/{chunks} error={msg.get('error')} detail={msg.get('detail')}",
                                flush=True,
                            )
                        continue
                    if mtype == "duplex.ack" and str(msg.get("frame_id")) == frame_id:
                        got_ack = True
                        ack_values.append(int(msg.get("ack_latency_ms") or 0))
                        if str(msg.get("status") or "") == "duplicate":
                            duplicate_count += 1
                        continue
                    if mtype == "duplex.turn":
                        data = msg.get("data", {})
                        if int((data or {}).get("seq") or 0) == seq:
                            if first_turn_ms is None:
                                first_turn_ms = max(1, int((time.perf_counter() - e2e_start) * 1000))
                            idx = int((data or {}).get("chunk_index") or 0)
                            if idx > 0:
                                chunk_turn_data[idx] = data
                            asr_data = (data or {}).get("asr", {}) if isinstance(data, dict) else {}
                            if isinstance(asr_data, dict):
                                provider = str(asr_data.get("provider") or "")
                                asr_meta = asr_data.get("asr_meta") or {}
                                reconnect_count = int((asr_meta or {}).get("reconnect_count") or 0) if isinstance(asr_meta, dict) else 0
                                providers.append(provider)
                                reconnect_counts.append(reconnect_count)
                                if verbose and idx > 0:
                                    print(
                                        f"[duplex] turn {seq}/{turns} chunk {idx}/{chunks} asr={int(asr_data.get('latency_ms') or 0)}ms provider={provider or 'unknown'} reused={bool((asr_meta or {}).get('connection_reused'))} reconnects={reconnect_count}",
                                        flush=True,
                                    )
                            if idx == chunks:
                                final_turn_data = data
                        continue
                    # Ignore stats/tts packets at this stage.
                if not is_final and sleep_ms > 0:
                    time.sleep(min(20, sleep_ms) / 1000)

            if server_drop_count > 0 and not final_turn_data:
                continue

            if not final_turn_data:
                deadline = time.perf_counter() + 20
                while time.perf_counter() < deadline:
                    msg = _recv_json_or_none(ws, timeout=5)
                    if msg is None:
                        continue
                    mtype = msg.get("type")
                    if mtype == "duplex.turn":
                        data = msg.get("data", {})
                        if int((data or {}).get("seq") or 0) == seq:
                            if first_turn_ms is None:
                                first_turn_ms = max(1, int((time.perf_counter() - e2e_start) * 1000))
                            idx = int((data or {}).get("chunk_index") or 0)
                            if idx > 0:
                                chunk_turn_data[idx] = data
                            asr_data = (data or {}).get("asr", {}) if isinstance(data, dict) else {}
                            if isinstance(asr_data, dict):
                                provider = str(asr_data.get("provider") or "")
                                asr_meta = asr_data.get("asr_meta") or {}
                                reconnect_count = int((asr_meta or {}).get("reconnect_count") or 0) if isinstance(asr_meta, dict) else 0
                                providers.append(provider)
                                reconnect_counts.append(reconnect_count)
                                if verbose and idx > 0:
                                    print(
                                        f"[duplex] turn {seq}/{turns} chunk {idx}/{chunks} asr={int(asr_data.get('latency_ms') or 0)}ms provider={provider or 'unknown'} reused={bool((asr_meta or {}).get('connection_reused'))} reconnects={reconnect_count}",
                                        flush=True,
                                    )
                            if idx == chunks:
                                final_turn_data = data
                                break
                    elif mtype == "duplex.error" and msg.get("error") == "server_busy":
                        server_drop_count += 1
                    elif mtype == "duplex.error" and verbose:
                        print(
                            f"[duplex] turn {seq}/{turns} wait-final error={msg.get('error')} detail={msg.get('detail')}",
                            flush=True,
                        )

            if not final_turn_data:
                if verbose:
                    print(f"[duplex] turn {seq}/{turns} missing final turn, skip", flush=True)
                continue

            data = final_turn_data
            asr = data.get("asr", {})
            event = data.get("event") or {}
            asr_values.append(int(asr.get("latency_ms") or 0))
            llm_values.append(int((event.get("latency_breakdown") or {}).get("llm_ms") or 0))

            tts_elapsed = 0
            followup = str((event or {}).get("followup_question") or "").strip()
            if followup:
                started_tts = time.perf_counter()
                while True:
                    msg = _recv_json_or_none(ws, timeout=2)
                    if msg is None:
                        break
                    mtype = msg.get("type")
                    if mtype == "duplex.tts.packet":
                        tts_elapsed = max(tts_elapsed, int((time.perf_counter() - started_tts) * 1000))
                        if bool(msg.get("is_final_packet")):
                            break
                    if mtype == "duplex.turn":
                        break

            tts_values.append(tts_elapsed)
            ttfb_values.append(first_turn_ms or int(asr.get("latency_ms") or 0) or 0)
            e2e_values.append(int((time.perf_counter() - e2e_start) * 1000))
            if verbose:
                print(
                    f"[duplex] turn {seq}/{turns} done ttfb={ttfb_values[-1]}ms asr={asr_values[-1]}ms llm={llm_values[-1]}ms tts={tts_values[-1]}ms e2e={e2e_values[-1]}ms ack={ack_values[-1] if ack_values else 0}ms",
                    flush=True,
                )
            if sleep_ms > 0:
                time.sleep(sleep_ms / 1000)

    return BenchmarkStats(
        asr_ms=asr_values,
        llm_ms=llm_values,
        tts_ms=tts_values,
        e2e_ms=e2e_values,
        ttfb_ms=ttfb_values,
        ack_ms=ack_values,
        duplicate_count=duplicate_count,
        server_drop_count=server_drop_count,
        sent_frames=turns,
        providers=providers,
        reconnect_counts=reconnect_counts,
    )


def _report(stats: BenchmarkStats) -> dict:
    ack_values = stats.ack_ms or []
    ttfb_values = stats.ttfb_ms or []
    total_frames = max(1, int(stats.sent_frames))
    ingest_success_rate = float(stats.ingest_success_count) / total_frames
    tts_published_rate = float(stats.tts_published_count) / total_frames
    providers = stats.providers or []
    provider_counts: dict[str, int] = {}
    for item in providers:
        key = item or "unknown"
        provider_counts[key] = provider_counts.get(key, 0) + 1
    reconnect_counts = stats.reconnect_counts or []
    return {
        "asr": {
            "p50": percentile(stats.asr_ms, 0.5),
            "p95": percentile(stats.asr_ms, 0.95),
            "p99": percentile(stats.asr_ms, 0.99),
            "samples": len(stats.asr_ms),
        },
        "llm": {
            "p50": percentile(stats.llm_ms, 0.5),
            "p95": percentile(stats.llm_ms, 0.95),
            "p99": percentile(stats.llm_ms, 0.99),
            "samples": len(stats.llm_ms),
        },
        "tts": {
            "p50": percentile(stats.tts_ms, 0.5),
            "p95": percentile(stats.tts_ms, 0.95),
            "p99": percentile(stats.tts_ms, 0.99),
            "samples": len(stats.tts_ms),
        },
        "e2e": {
            "p50": percentile(stats.e2e_ms, 0.5),
            "p95": percentile(stats.e2e_ms, 0.95),
            "p99": percentile(stats.e2e_ms, 0.99),
            "samples": len(stats.e2e_ms),
        },
        "ttfb": {
            "p50": percentile(ttfb_values, 0.5),
            "p95": percentile(ttfb_values, 0.95),
            "p99": percentile(ttfb_values, 0.99),
            "samples": len(ttfb_values),
        },
        "ack": {
            "p50": percentile(ack_values, 0.5),
            "p95": percentile(ack_values, 0.95),
            "p99": percentile(ack_values, 0.99),
            "samples": len(ack_values),
        },
        "loss": {
            "duplicate_count": int(stats.duplicate_count),
            "server_drop_count": int(stats.server_drop_count),
            "drop_rate": round(float(stats.server_drop_count) / total_frames, 4),
        },
        "asr_transport": {
            "provider_counts": provider_counts,
            "reconnect_total": int(sum(reconnect_counts)),
            "reconnect_p95": percentile(reconnect_counts, 0.95),
        },
        "room_ingest": {
            "ingest_success_count": int(stats.ingest_success_count),
            "ingest_success_rate": round(ingest_success_rate, 4),
            "tts_published_count": int(stats.tts_published_count),
            "tts_published_rate": round(tts_published_rate, 4),
            "preflight_accepted_count": int(stats.preflight_accepted_count),
        },
    }


def _evaluate_sla(
    report: dict,
    *,
    asr_p95_max: int,
    llm_p95_max: int,
    tts_p95_max: int,
    e2e_p95_max: int,
    min_ingest_success_rate: float,
    min_tts_publish_rate: float,
) -> dict:
    checks = {
        "asr_p95": float((report.get("asr") or {}).get("p95") or 0) <= float(asr_p95_max),
        "llm_p95": float((report.get("llm") or {}).get("p95") or 0) <= float(llm_p95_max),
        "tts_p95": float((report.get("tts") or {}).get("p95") or 0) <= float(tts_p95_max),
        "e2e_p95": float((report.get("e2e") or {}).get("p95") or 0) <= float(e2e_p95_max),
        "ingest_success_rate": float((report.get("room_ingest") or {}).get("ingest_success_rate") or 0)
        >= float(min_ingest_success_rate),
        "tts_publish_rate": float((report.get("room_ingest") or {}).get("tts_published_rate") or 0)
        >= float(min_tts_publish_rate),
    }
    return {"pass": all(checks.values()), "checks": checks}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI interview realtime benchmark")
    parser.add_argument("--base-url", default=os.getenv("AI_HR_BENCH_BASE_URL", "http://127.0.0.1:8000/api/v1"))
    parser.add_argument("--turns", type=int, default=10)
    parser.add_argument("--sleep-ms", type=int, default=120)
    parser.add_argument("--mode", choices=["legacy", "duplex", "room_ingest", "compare"], default="compare")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--duplex-chunks", type=int, default=2)
    parser.add_argument("--frame-ms", type=int, default=120)
    parser.add_argument("--room-ingest-with-preflight", action="store_true")
    parser.add_argument("--sla-asr-p95-max-ms", type=int, default=1200)
    parser.add_argument("--sla-llm-p95-max-ms", type=int, default=1600)
    parser.add_argument("--sla-tts-p95-max-ms", type=int, default=1800)
    parser.add_argument("--sla-e2e-p95-max-ms", type=int, default=2600)
    parser.add_argument("--sla-min-ingest-success-rate", type=float, default=0.98)
    parser.add_argument("--sla-min-tts-publish-rate", type=float, default=0.95)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    mode = args.mode
    result: dict[str, dict] = {}

    if mode in {"legacy", "compare"}:
        legacy_stats = run_benchmark_legacy(
            base_url=args.base_url,
            turns=max(1, args.turns),
            sleep_ms=max(0, args.sleep_ms),
            verbose=bool(args.verbose),
        )
        result["legacy"] = _report(legacy_stats)

    if mode in {"duplex", "compare"}:
        duplex_stats = run_benchmark_duplex(
            base_url=args.base_url,
            turns=max(1, args.turns),
            sleep_ms=max(0, args.sleep_ms),
            verbose=bool(args.verbose),
            duplex_chunks=max(1, int(args.duplex_chunks)),
            frame_ms=max(30, int(args.frame_ms)),
        )
        result["duplex"] = _report(duplex_stats)

    if mode == "room_ingest":
        room_ingest_stats = run_benchmark_room_ingest(
            base_url=args.base_url,
            turns=max(1, args.turns),
            sleep_ms=max(0, args.sleep_ms),
            verbose=bool(args.verbose),
            with_preflight=bool(args.room_ingest_with_preflight),
        )
        result["room_ingest"] = _report(room_ingest_stats)

    if mode == "compare" and "legacy" in result and "duplex" in result:
        result["delta"] = {
            "asr_p95_ms": result["duplex"]["asr"]["p95"] - result["legacy"]["asr"]["p95"],
            "asr_p99_ms": result["duplex"]["asr"]["p99"] - result["legacy"]["asr"]["p99"],
            "llm_p95_ms": result["duplex"]["llm"]["p95"] - result["legacy"]["llm"]["p95"],
            "llm_p99_ms": result["duplex"]["llm"]["p99"] - result["legacy"]["llm"]["p99"],
            "tts_p95_ms": result["duplex"]["tts"]["p95"] - result["legacy"]["tts"]["p95"],
            "tts_p99_ms": result["duplex"]["tts"]["p99"] - result["legacy"]["tts"]["p99"],
            "e2e_p95_ms": result["duplex"]["e2e"]["p95"] - result["legacy"]["e2e"]["p95"],
            "e2e_p99_ms": result["duplex"]["e2e"]["p99"] - result["legacy"]["e2e"]["p99"],
            "ttfb_p95_ms": result["duplex"]["ttfb"]["p95"] - result["legacy"]["ttfb"]["p95"],
            "ack_p95_ms": result["duplex"]["ack"]["p95"] - result["legacy"]["ack"]["p95"],
        }

    selected_report = (
        result.get("room_ingest")
        or result.get("duplex")
        or result.get("legacy")
        or {}
    )
    if selected_report:
        result["sla"] = _evaluate_sla(
            selected_report,
            asr_p95_max=max(1, int(args.sla_asr_p95_max_ms)),
            llm_p95_max=max(1, int(args.sla_llm_p95_max_ms)),
            tts_p95_max=max(1, int(args.sla_tts_p95_max_ms)),
            e2e_p95_max=max(1, int(args.sla_e2e_p95_max_ms)),
            min_ingest_success_rate=max(0.0, min(1.0, float(args.sla_min_ingest_success_rate))),
            min_tts_publish_rate=max(0.0, min(1.0, float(args.sla_min_tts_publish_rate))),
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
