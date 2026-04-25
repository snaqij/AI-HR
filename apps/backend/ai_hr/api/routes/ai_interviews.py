"""AI interview routes."""

from __future__ import annotations

import asyncio
import logging
import json
import time
import uuid
from datetime import UTC, datetime
from collections import deque
from typing import Any
from fastapi import APIRouter, Depends, Query, status
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from pydantic import ValidationError
from sqlalchemy.orm import Session
from ...core.config import get_settings
from ...core.responses import Envelope
from ...core.security import require_ai_interview_auth, require_ai_interview_ws_auth
from ...db.session import get_db_session
from ...schemas.ai_interviews import (
    AIInterviewASRStreamRequest,
    AIInterviewASRStreamResponse,
    AIInterviewQuestionGenerateRequest,
    AIInterviewQuestionGenerateResult,
    AIInterviewQuestionPackPrebuildRequest,
    AIInterviewQuestionPackPrebuildResult,
    AIInterviewMetricsResponse,
    AIInterviewRTCAudioSubscribeRequest,
    AIInterviewRTCAudioSubscribeResponse,
    AIInterviewRTCASRIngestRequest,
    AIInterviewRTCASRIngestResponse,
    AIInterviewRTCVideoPolicyRequest,
    AIInterviewRTCVideoPolicyResponse,
    AIInterviewRTCJoinRequest,
    AIInterviewRTCJoinResponse,
    AIInterviewRTCReconnectRequest,
    AIInterviewRTCReconnectResponse,
    AIInterviewTENRuntimeResponse,
    AIInterviewReplayResponse,
    AIInterviewReportResponse,
    AIInterviewSessionCreateRequest,
    AIInterviewSessionCreateResult,
    AIInterviewSessionEventRequest,
    AIInterviewSessionEventResult,
    AIInterviewSessionFinishRequest,
    AIInterviewSessionHandoffRequest,
    AIInterviewSessionHandoffResult,
    AIInterviewSessionResponse,
    AIInterviewSessionStartRequest,
    AIInterviewTTSStreamRequest,
    AIInterviewTTSStreamResponse,
)
from ...services.ai_interviews import get_ai_interview_service
from ...services.orchestrator.event_bus import DEFAULT_INTERVIEW_EVENT_BUS

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/ai/interviews",
    tags=["ai-interviews"],
    dependencies=[Depends(require_ai_interview_auth)],
)


class BridgeEventPayload(BaseModel):
    event_id: str | None = None
    event_type: str
    session_id: str | None = None
    ts: int | None = None
    source: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class BridgeBatchRequest(BaseModel):
    events: list[BridgeEventPayload] = Field(default_factory=list)


@router.post("/question-packs/prebuild", response_model=Envelope[AIInterviewQuestionPackPrebuildResult])
def prebuild_ai_interview_question_pack(
    payload: AIInterviewQuestionPackPrebuildRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[AIInterviewQuestionPackPrebuildResult]:
    """Route handler."""
    service = get_ai_interview_service(session)
    result = service.prebuild_question_pack(payload)
    return Envelope.success(AIInterviewQuestionPackPrebuildResult.model_validate(result))


@router.post("/sessions", response_model=Envelope[AIInterviewSessionCreateResult], status_code=status.HTTP_201_CREATED)
def create_ai_interview_session(
    payload: AIInterviewSessionCreateRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[AIInterviewSessionCreateResult]:
    """Route handler."""
    service = get_ai_interview_service(session)
    result = service.create_session(payload)
    return Envelope.success(AIInterviewSessionCreateResult(session=AIInterviewSessionResponse.model_validate(result)))


@router.get("/sessions/{session_id}", response_model=Envelope[AIInterviewSessionResponse])
def get_ai_interview_session(
    session_id: str,
    session: Session = Depends(get_db_session),
) -> Envelope[AIInterviewSessionResponse]:
    """Route handler."""
    service = get_ai_interview_service(session)
    result = service.get_session(session_id)
    return Envelope.success(AIInterviewSessionResponse.model_validate(result))


@router.post("/sessions/{session_id}/start", response_model=Envelope[AIInterviewSessionResponse])
def start_ai_interview_session(
    session_id: str,
    payload: AIInterviewSessionStartRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[AIInterviewSessionResponse]:
    """Route handler."""
    service = get_ai_interview_service(session)
    result = service.start_session(session_id, payload)
    return Envelope.success(AIInterviewSessionResponse.model_validate(result))


@router.post("/sessions/{session_id}/finish", response_model=Envelope[AIInterviewSessionResponse])
def finish_ai_interview_session(
    session_id: str,
    payload: AIInterviewSessionFinishRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[AIInterviewSessionResponse]:
    """Route handler."""
    service = get_ai_interview_service(session)
    result = service.finish_session(session_id, payload)
    return Envelope.success(AIInterviewSessionResponse.model_validate(result))


@router.post("/sessions/{session_id}/handoff", response_model=Envelope[AIInterviewSessionHandoffResult])
def handoff_ai_interview_session(
    session_id: str,
    payload: AIInterviewSessionHandoffRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[AIInterviewSessionHandoffResult]:
    """Route handler."""
    service = get_ai_interview_service(session)
    result = service.handoff_session(session_id, payload)
    return Envelope.success(
        AIInterviewSessionHandoffResult(
            session=AIInterviewSessionResponse.model_validate(result["session"]),
            handoff_id=result["handoff_id"],
        )
    )


@router.post("/sessions/{session_id}/events", response_model=Envelope[AIInterviewSessionEventResult])
def append_ai_interview_event(
    session_id: str,
    payload: AIInterviewSessionEventRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[AIInterviewSessionEventResult]:
    """Route handler."""
    service = get_ai_interview_service(session)
    result = service.append_event(session_id, payload)
    return Envelope.success(AIInterviewSessionEventResult.model_validate(result))


@router.post("/sessions/{session_id}/bridge/events", response_model=Envelope[dict[str, int]])
def append_ai_interview_bridge_events(
    session_id: str,
    payload: BridgeBatchRequest,
) -> Envelope[dict[str, int]]:
    """Ingest realtime bridge events emitted by TEN sidecar without blocking the audio path."""
    print(
        "[BRIDGE][request] "
        f"session_id={session_id} events_count={len(payload.events)}",
        flush=True,
    )
    accepted = 0
    for item in payload.events:
        event_session_id = str(item.session_id or session_id).strip()
        if event_session_id != session_id:
            print(
                "[BRIDGE][drop] "
                f"path_session_id={session_id} event_session_id={event_session_id} "
                f"event_type={str(item.event_type or '').strip()}",
                flush=True,
            )
            continue
        bridge_event_type = str(item.event_type or "").strip()
        bridge_payload = dict(item.payload or {})
        if "occurred_at" not in bridge_payload:
            if item.ts is not None:
                try:
                    bridge_payload["occurred_at"] = datetime.fromtimestamp(float(item.ts) / 1000.0, tz=UTC).isoformat()
                except (TypeError, ValueError):
                    bridge_payload["occurred_at"] = datetime.now(tz=UTC).isoformat()
            else:
                bridge_payload["occurred_at"] = datetime.now(tz=UTC).isoformat()
        print(
            "[BRIDGE][accept] "
            f"session_id={session_id} event_type={bridge_event_type} "
            f"source={item.source or 'ten_agent'} payload_keys={list(bridge_payload.keys())}",
            flush=True,
        )
        DEFAULT_INTERVIEW_EVENT_BUS.publish(
            session_id=session_id,
            event_type=bridge_event_type,
            payload={
                **bridge_payload,
                "event_id": item.event_id,
                "source": item.source or "ten_agent",
                "bridge_ts": item.ts,
            },
        )
        accepted += 1
    print(
        "[BRIDGE][response] "
        f"session_id={session_id} accepted={accepted} total={len(payload.events)}",
        flush=True,
    )
    return Envelope.success({"accepted": accepted})


@router.post("/sessions/{session_id}/question-set/generate", response_model=Envelope[AIInterviewQuestionGenerateResult])
def generate_ai_interview_question_set(
    session_id: str,
    payload: AIInterviewQuestionGenerateRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[AIInterviewQuestionGenerateResult]:
    """Route handler."""
    service = get_ai_interview_service(session)
    result = service.generate_question_set(session_id=session_id, payload=payload)
    return Envelope.success(AIInterviewQuestionGenerateResult.model_validate(result))


@router.get("/sessions/{session_id}/report", response_model=Envelope[AIInterviewReportResponse])
def get_ai_interview_report(
    session_id: str,
    run_id: str | None = Query(default=None),
    force_recompute: bool = Query(default=False),
    session: Session = Depends(get_db_session),
) -> Envelope[AIInterviewReportResponse]:
    """Route handler."""
    service = get_ai_interview_service(session)
    result = service.get_report(session_id, run_id=run_id, force_recompute=force_recompute)
    return Envelope.success(result)


@router.get("/sessions/{session_id}/replay", response_model=Envelope[AIInterviewReplayResponse])
def get_ai_interview_replay(
    session_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
) -> Envelope[AIInterviewReplayResponse]:
    """Route handler."""
    service = get_ai_interview_service(session)
    result = service.get_replay(session_id, limit=limit, offset=offset)
    return Envelope.success(result)


@router.get("/metrics", response_model=Envelope[AIInterviewMetricsResponse])
def get_ai_interview_metrics(
    window_minutes: int = Query(default=60, ge=1, le=24 * 60),
    min_samples: int = Query(default=5, ge=1, le=1000),
    session: Session = Depends(get_db_session),
) -> Envelope[AIInterviewMetricsResponse]:
    """Route handler."""
    service = get_ai_interview_service(session)
    result = service.get_metrics(window_minutes=window_minutes, min_samples=min_samples)
    return Envelope.success(result)


@router.post("/sessions/{session_id}/rtc/join", response_model=Envelope[AIInterviewRTCJoinResponse])
def rtc_join_ai_interview_session(
    session_id: str,
    payload: AIInterviewRTCJoinRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[AIInterviewRTCJoinResponse]:
    """Route handler."""
    service = get_ai_interview_service(session)
    result = service.rtc_join(session_id, payload)
    return Envelope.success(result)


@router.get("/sessions/{session_id}/ten/runtime-config", response_model=Envelope[AIInterviewTENRuntimeResponse])
def get_ai_interview_ten_runtime_config(
    session_id: str,
    session: Session = Depends(get_db_session),
) -> Envelope[AIInterviewTENRuntimeResponse]:
    """Route handler."""
    service = get_ai_interview_service(session)
    result = service.get_ten_runtime_config(session_id)
    return Envelope.success(result)


@router.post("/sessions/{session_id}/ten/launch", response_model=Envelope[AIInterviewTENRuntimeResponse])
def launch_ai_interview_ten_session(
    session_id: str,
    session: Session = Depends(get_db_session),
) -> Envelope[AIInterviewTENRuntimeResponse]:
    """Route handler."""
    service = get_ai_interview_service(session)
    result = service.launch_ten_session(session_id)
    return Envelope.success(result)


@router.post("/sessions/{session_id}/rtc/reconnect", response_model=Envelope[AIInterviewRTCReconnectResponse])
def rtc_reconnect_ai_interview_session(
    session_id: str,
    payload: AIInterviewRTCReconnectRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[AIInterviewRTCReconnectResponse]:
    """Route handler."""
    service = get_ai_interview_service(session)
    result = service.rtc_reconnect(session_id, payload)
    return Envelope.success(result)


@router.post("/sessions/{session_id}/rtc/audio/subscribe", response_model=Envelope[AIInterviewRTCAudioSubscribeResponse])
def rtc_subscribe_audio_ai_interview_session(
    session_id: str,
    payload: AIInterviewRTCAudioSubscribeRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[AIInterviewRTCAudioSubscribeResponse]:
    """Route handler."""
    service = get_ai_interview_service(session)
    result = service.rtc_subscribe_audio(session_id, payload)
    return Envelope.success(result)


@router.post("/sessions/{session_id}/rtc/video/policy", response_model=Envelope[AIInterviewRTCVideoPolicyResponse])
def rtc_apply_video_policy_ai_interview_session(
    session_id: str,
    payload: AIInterviewRTCVideoPolicyRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[AIInterviewRTCVideoPolicyResponse]:
    """Route handler."""
    service = get_ai_interview_service(session)
    result = service.rtc_apply_video_policy(session_id, payload)
    return Envelope.success(result)


@router.post("/sessions/{session_id}/rtc/asr/stream", response_model=Envelope[AIInterviewASRStreamResponse])
def rtc_asr_stream_ai_interview_session(
    session_id: str,
    payload: AIInterviewASRStreamRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[AIInterviewASRStreamResponse]:
    """Route handler."""
    service = get_ai_interview_service(session)
    result = service.asr_stream(session_id, payload)
    return Envelope.success(result)


@router.post("/sessions/{session_id}/rtc/tts/stream", response_model=Envelope[AIInterviewTTSStreamResponse])
def rtc_tts_stream_ai_interview_session(
    session_id: str,
    payload: AIInterviewTTSStreamRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[AIInterviewTTSStreamResponse]:
    """Route handler."""
    service = get_ai_interview_service(session)
    result = service.tts_stream(session_id, payload)
    return Envelope.success(result)


@router.post("/rtc/asr/ingest", response_model=Envelope[AIInterviewRTCASRIngestResponse])
def rtc_ingest_audio_frame(
    payload: AIInterviewRTCASRIngestRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[AIInterviewRTCASRIngestResponse]:
    """Route handler."""
    service = get_ai_interview_service(session)
    result = service.rtc_ingest_audio(payload)
    return Envelope.success(AIInterviewRTCASRIngestResponse.model_validate(result))


@router.websocket("/rtc/asr/ingest/ws")
async def ws_rtc_ingest_audio(
    websocket: WebSocket,
    session: Session = Depends(get_db_session),
) -> None:
    """Route handler."""
    if not await require_ai_interview_ws_auth(websocket):
        return
    settings = get_settings()
    if not settings.ai_interview_rtc_asr_ingest_ws_enabled:
        await websocket.close(code=4403, reason="rtc_asr_ingest_ws_disabled")
        return

    service = get_ai_interview_service(session)
    await websocket.accept()
    seen_frame_ids: set[str] = set()
    seen_frame_queue: deque[str] = deque()
    max_seen_frames = max(512, int(settings.ai_interview_duplex_seen_frame_window))
    await websocket.send_json({"type": "ingest.connected", "version": "v1"})

    def _remember_frame_id(frame_id: str) -> None:
        seen_frame_ids.add(frame_id)
        seen_frame_queue.append(frame_id)
        while len(seen_frame_queue) > max_seen_frames:
            old_frame_id = seen_frame_queue.popleft()
            seen_frame_ids.discard(old_frame_id)

    def _normalize_payload(raw: dict) -> dict:
        if "payload" in raw and isinstance(raw.get("payload"), dict):
            return dict(raw["payload"])
        return raw

    def _serialize_result(result: dict) -> dict:
        asr = result.get("asr")
        event = result.get("event")
        tts = result.get("tts")
        asr_data = asr.model_dump() if hasattr(asr, "model_dump") else dict(asr or {})
        event_data = event.model_dump() if hasattr(event, "model_dump") else (dict(event or {}) if event else None)
        tts_data = tts.model_dump() if hasattr(tts, "model_dump") else (dict(tts or {}) if tts else None)
        return {
            "session_id": result.get("session_id"),
            "room_id": result.get("room_id"),
            "asr": asr_data,
            "event": event_data,
            "tts": tts_data,
        }

    try:
        while True:
            message = await websocket.receive_text()
            recv_start = time.perf_counter()
            try:
                raw = json.loads(message)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "ingest.error", "error": "invalid_json"})
                continue
            if not isinstance(raw, dict):
                await websocket.send_json({"type": "ingest.error", "error": "invalid_payload"})
                continue
            msg_type = str(raw.get("type") or "").strip().lower()
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            if msg_type and msg_type not in {"audio_frame", "ingest"}:
                await websocket.send_json({"type": "ingest.error", "error": "unsupported_message_type"})
                continue

            normalized = _normalize_payload(raw)
            frame_id = str(normalized.get("frame_id") or "").strip()
            if frame_id and frame_id in seen_frame_ids:
                await websocket.send_json(
                    {
                        "type": "ingest.ack",
                        "frame_id": frame_id,
                        "status": "duplicate",
                        "ack_latency_ms": max(1, int((time.perf_counter() - recv_start) * 1000)),
                    }
                )
                continue
            try:
                ingest_req = AIInterviewRTCASRIngestRequest.model_validate(normalized)
            except ValidationError as exc:
                await websocket.send_json({"type": "ingest.error", "error": "validation_error", "detail": str(exc)})
                continue

            if frame_id:
                _remember_frame_id(frame_id)
            await websocket.send_json(
                {
                    "type": "ingest.ack",
                    "frame_id": frame_id or ingest_req.frame_id,
                    "room_id": ingest_req.room_id,
                    "seq": ingest_req.seq,
                    "status": "accepted",
                    "ack_latency_ms": max(1, int((time.perf_counter() - recv_start) * 1000)),
                }
            )
            try:
                result = await asyncio.to_thread(service.rtc_ingest_audio, ingest_req)
                await websocket.send_json({"type": "ingest.result", "data": _serialize_result(result)})
            except Exception as exc:
                session.rollback()
                await websocket.send_json({"type": "ingest.error", "error": "ingest_failed", "detail": str(exc)})
    except WebSocketDisconnect:
        return


@router.websocket("/sessions/{session_id}/events/ws")
async def ws_ai_interview_events(session_id: str, websocket: WebSocket) -> None:
    """Route handler."""
    if not await require_ai_interview_ws_auth(websocket):
        return
    await websocket.accept()
    DEFAULT_INTERVIEW_EVENT_BUS.bind_loop(asyncio.get_running_loop())
    subscription = DEFAULT_INTERVIEW_EVENT_BUS.subscribe(session_id=session_id)
    def _make_json_safe(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: _make_json_safe(v) for k, v in obj.items() if not isinstance(v, bytes)}
        if isinstance(obj, (list, tuple)):
            return [_make_json_safe(i) for i in obj if not isinstance(i, bytes)]
        return obj

    try:
        await websocket.send_json({"event_type": "connected", "session_id": session_id})
        while True:
            try:
                event = await asyncio.wait_for(subscription.queue.get(), timeout=25)
                # Ensure the payload is JSON serializable by stripping bytes
                safe_event = _make_json_safe(event)
                await websocket.send_json(safe_event)
            except asyncio.TimeoutError:
                await websocket.send_json({"event_type": "ping", "session_id": session_id})
    except WebSocketDisconnect:
        return
    finally:
        DEFAULT_INTERVIEW_EVENT_BUS.unsubscribe(subscription)


@router.websocket("/sessions/{session_id}/rtc/duplex/ws")
async def ws_ai_interview_duplex(
    session_id: str,
    websocket: WebSocket,
    session: Session = Depends(get_db_session),
) -> None:
    """Route handler."""
    if not await require_ai_interview_ws_auth(websocket):
        return
    settings = get_settings()
    if not settings.ai_interview_rtc_duplex_ws_enabled:
        await websocket.close(code=4403, reason="duplex_ws_disabled")
        return

    websocket_closed = False
    send_lock = asyncio.Lock()
    service = get_ai_interview_service(session)

    event_sub = None
    listener_task: asyncio.Task | None = None
    dispatcher_task: asyncio.Task | None = None
    audio_consumer_task: asyncio.Task | None = None
    pending_finalize_task: asyncio.Task | None = None

    seen_frame_ids: set[str] = set()
    seen_frame_queue: deque[str] = deque()
    max_seen_frames = 1000

    accepted_count = 0
    duplicate_count = 0
    server_drop_count = 0
    received_audio_chunks = 0
    stats_emit_every = 20

    ack_latencies_ms: list[int] = []
    asr_latencies_ms: list[int] = []
    llm_latencies_ms: list[int] = []
    tts_latencies_ms: list[int] = []
    e2e_latencies_ms: list[int] = []

    audio_chunk_queue: asyncio.Queue[tuple[dict[str, Any], bytes | None, float]] = asyncio.Queue(maxsize=128)
    packet_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=512)

    interrupt_generation = 0
    candidate_last_spoken_at = 0.0
    active_generation_id = 0
    latest_received_seq = 0
    last_flushed_seq = 0

    def _percentile(values: list[int], p: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        rank = max(1, min(len(ordered), int(len(ordered) * p + 0.9999)))
        return float(ordered[rank - 1])

    def _latency_summary(values: list[int]) -> dict[str, Any]:
        return {
            "p50": _percentile(values, 0.50),
            "p95": _percentile(values, 0.95),
            "p99": _percentile(values, 0.99),
            "samples": len(values),
        }

    async def _safe_send(payload: dict[str, Any]) -> bool:
        nonlocal websocket_closed
        if websocket_closed:
            return False
        async with send_lock:
            try:
                await websocket.send_json(payload)
                return True
            except (WebSocketDisconnect, RuntimeError):
                websocket_closed = True
                return False

    async def _safe_send_bytes(data: bytes) -> bool:
        nonlocal websocket_closed
        if websocket_closed:
            return False
        async with send_lock:
            try:
                await websocket.send_bytes(data)
                return True
            except (WebSocketDisconnect, RuntimeError):
                websocket_closed = True
                return False

    async def _emit_stats() -> None:
        if websocket_closed:
            return
        processed_total = accepted_count + duplicate_count + server_drop_count
        drop_rate = (server_drop_count / processed_total) if processed_total else 0.0
        await _safe_send(
            {
                "type": "duplex.stats",
                "session_id": session_id,
                "ack": _latency_summary(ack_latencies_ms),
                "loss": {
                    "server_drop_count": server_drop_count,
                    "duplicate_count": duplicate_count,
                    "received_audio_chunks": received_audio_chunks,
                    "server_drop_rate": round(drop_rate, 4),
                },
                "latency": {
                    "asr": _latency_summary(asr_latencies_ms),
                    "llm": _latency_summary(llm_latencies_ms),
                    "tts": _latency_summary(tts_latencies_ms),
                    "e2e": _latency_summary(e2e_latencies_ms),
                },
            }
        )

    async def _emit_stats_if_needed() -> None:
        processed_total = accepted_count + duplicate_count + server_drop_count
        if processed_total > 0 and processed_total % stats_emit_every == 0:
            await _emit_stats()

    def _remember_frame_id(frame_id: str) -> None:
        seen_frame_ids.add(frame_id)
        seen_frame_queue.append(frame_id)
        while len(seen_frame_queue) > max_seen_frames:
            seen_frame_ids.discard(seen_frame_queue.popleft())

    def _clear_packet_queue() -> None:
        while True:
            try:
                packet_queue.get_nowait()
                packet_queue.task_done()
            except asyncio.QueueEmpty:
                break

    def _decode_inbound(raw_msg: dict[str, Any]) -> tuple[dict[str, Any], bytes | None] | None:
        if raw_msg.get("type") == "websocket.disconnect":
            return None
        if "text" in raw_msg and raw_msg.get("text") is not None:
            try:
                parsed = json.loads(raw_msg["text"])
            except Exception:
                return ({}, None)
            if isinstance(parsed, dict):
                return (parsed, None)
            return ({}, None)
        if "bytes" in raw_msg and raw_msg.get("bytes") is not None:
            bdata = raw_msg["bytes"]
            if not isinstance(bdata, (bytes, bytearray)) or len(bdata) < 2:
                return ({}, None)
            json_len = int.from_bytes(bytes(bdata[:2]), "big")
            if len(bdata) < 2 + json_len:
                return ({}, None)
            try:
                payload = json.loads(bytes(bdata[2 : 2 + json_len]).decode("utf-8"))
            except Exception:
                return ({}, None)
            if not isinstance(payload, dict):
                return ({}, None)
            return (payload, bytes(bdata[2 + json_len :]))
        return ({}, None)

    def _safe_flush_asr(seq: int) -> None:
        nonlocal last_flushed_seq
        if seq <= last_flushed_seq:
            return
        last_flushed_seq = seq
        from ...db.session import SessionLocal

        with SessionLocal() as local_session:
            local_service = get_ai_interview_service(local_session)
            local_service.process_duplex_end_of_turn(session_id=session_id, seq=seq, payload={"source": "backend_vad"})

    async def _run_event_bus_listener() -> None:
        nonlocal interrupt_generation, candidate_last_spoken_at, active_generation_id, pending_finalize_task
        assert event_sub is not None
        try:
            while not websocket_closed:
                try:
                    event = await asyncio.wait_for(event_sub.queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                event_type = str(event.get("event_type") or "").strip()
                payload = event.get("payload", {})
                if not isinstance(payload, dict):
                    payload = {}

                if event_type == "asr.turn":
                    candidate_last_spoken_at = time.perf_counter()
                    active_generation_id += 1
                    local_generation_id = active_generation_id
                    if pending_finalize_task and not pending_finalize_task.done():
                        pending_finalize_task.cancel()

                    if payload:
                        await _safe_send({"type": "duplex.asr.turn", "data": payload})

                    if not bool(payload.get("is_final")):
                        continue

                    transcript = str(payload.get("transcript") or "").strip()
                    seq = int(payload.get("seq") or 1)
                    from ai_hr.services.interview_runtime.semantic_endpoint import evaluate_semantic_floor

                    floor_action = evaluate_semantic_floor(transcript, stage="S3")

                    async def _debounced_append_event(
                        generation_id: int,
                        event_payload: dict[str, Any],
                        transcript_text: str,
                        event_seq: int,
                    ) -> None:
                        delay = 1.0 if floor_action == "HOLD" else 0.3
                        await asyncio.sleep(delay)
                        if active_generation_id != generation_id:
                            return

                        def _run_append() -> None:
                            from ...db.session import SessionLocal
                            from ...schemas.ai_interviews import AIInterviewSessionEventRequest

                            with SessionLocal() as local_session:
                                local_service = get_ai_interview_service(local_session)
                                event_req = AIInterviewSessionEventRequest(
                                    event_id=str(event_payload.get("event_id") or uuid.uuid4().hex),
                                    seq=max(1, event_seq),
                                    speaker="candidate",
                                    transcript=transcript_text,
                                    confidence=float(event_payload.get("confidence") or 0.9),
                                    payload=event_payload,
                                )
                                local_service.append_event(session_id, event_req)

                        try:
                            await asyncio.to_thread(_run_append)
                        except Exception:
                            logger.exception(
                                "ai_interview.ws.bridge_thread_error trace_id=%s session_id=%s",
                                session_id,
                                session_id,
                            )

                    pending_finalize_task = asyncio.create_task(
                        _debounced_append_event(
                            generation_id=local_generation_id,
                            event_payload=dict(payload),
                            transcript_text=transcript,
                            event_seq=seq,
                        ),
                        name=f"duplex-finalize-{session_id}-{local_generation_id}",
                    )
                    continue

                if event_type == "tts.packet":
                    if not packet_queue.full():
                        packet = dict(payload)
                        packet["produced_at"] = time.perf_counter()
                        await packet_queue.put(packet)
                    continue

                if event_type == "llm.sentence":
                    if payload:
                        latency_ms = payload.get("latency_ms")
                        if isinstance(latency_ms, int) and latency_ms > 0:
                            llm_latencies_ms.append(int(latency_ms))
                        await _safe_send({"type": "duplex.llm.sentence", "data": payload})
                    continue

                if event_type == "tts.interrupt":
                    interrupt_generation += 1
                    _clear_packet_queue()
                    await _safe_send({"type": "duplex.tts.interrupt", "session_id": session_id})
                    continue
        except asyncio.CancelledError:
            return
        except Exception as exc:
            if not websocket_closed:
                logger.error("Event bus listener error: %s", exc)

    async def _run_tts_dispatcher() -> None:
        nonlocal interrupt_generation
        packet_index = 0
        prev_sent_at: float | None = None
        local_interrupt_generation = interrupt_generation
        coalesce_target_bytes = int(16000 * 2 * 0.02)
        coalesce_bytes = bytearray()
        coalesce_sample_rate = 16000
        coalesce_text = ""
        coalesce_final = False
        coalesce_deadline = 0.0
        coalesce_first_produced_at: float | None = None
        coalesce_tts_first_pcm_at_ms: int | None = None

        def _reset_coalesce_state() -> None:
            nonlocal coalesce_bytes, coalesce_text, coalesce_final, coalesce_deadline
            nonlocal coalesce_first_produced_at, coalesce_tts_first_pcm_at_ms
            coalesce_bytes = bytearray()
            coalesce_text = ""
            coalesce_final = False
            coalesce_deadline = 0.0
            coalesce_first_produced_at = None
            coalesce_tts_first_pcm_at_ms = None

        async def _flush(now: float) -> None:
            nonlocal packet_index, prev_sent_at
            nonlocal coalesce_bytes, coalesce_text, coalesce_final, coalesce_sample_rate
            nonlocal coalesce_first_produced_at, coalesce_tts_first_pcm_at_ms, coalesce_deadline
            if not coalesce_bytes:
                return
            packet_index += 1
            produced_at = coalesce_first_produced_at if coalesce_first_produced_at is not None else now
            packet_latency_ms = max(0, int((now - produced_at) * 1000))
            inter_packet_gap_ms = 0
            if prev_sent_at is not None:
                inter_packet_gap_ms = max(0, int((now - prev_sent_at) * 1000))
            prev_sent_at = now
            tts_latencies_ms.append(packet_latency_ms)
            await _safe_send(
                {
                    "type": "duplex.tts.packet",
                    "session_id": session_id,
                    "packet_index": packet_index,
                    "is_final_packet": bool(coalesce_final),
                    "text": coalesce_text,
                    "transport": "binary",
                    "audio_uri": "",
                    "audio_codec": "pcm",
                    "sample_rate": int(coalesce_sample_rate or 16000),
                    "packet_latency_ms": packet_latency_ms,
                    "inter_packet_gap_ms": inter_packet_gap_ms,
                    "tts_first_pcm_at_ms": int(coalesce_tts_first_pcm_at_ms or 0),
                }
            )
            await _safe_send_bytes(bytes(coalesce_bytes))
            _reset_coalesce_state()

        try:
            while not websocket_closed:
                try:
                    if local_interrupt_generation != interrupt_generation:
                        local_interrupt_generation = interrupt_generation
                        _reset_coalesce_state()

                    wait_timeout = 0.02
                    if coalesce_bytes and coalesce_deadline > 0:
                        wait_timeout = max(0.005, min(0.02, coalesce_deadline - time.perf_counter()))

                    packet = await asyncio.wait_for(packet_queue.get(), timeout=wait_timeout)
                    if packet.get("_error"):
                        await _safe_send(
                            {"type": "duplex.error", "error": "tts_stream_failed", "detail": packet.get("_error")}
                        )
                        continue

                    now = time.perf_counter()
                    produced_at = float(packet.get("produced_at") or now)
                    packet_latency_ms = max(0, int((now - produced_at) * 1000))
                    audio_bytes = packet.get("audio_bytes")
                    if not isinstance(audio_bytes, (bytes, bytearray)) or len(audio_bytes) == 0:
                        await _safe_send({"type": "duplex.error", "error": "tts_packet_invalid_audio_bytes"})
                        continue

                    audio_codec = str(packet.get("audio_codec") or "").strip().lower()
                    if audio_codec and audio_codec != "pcm":
                        await _safe_send(
                            {
                                "type": "duplex.error",
                                "error": "tts_packet_invalid_audio_codec",
                                "detail": f"expected pcm, got {audio_codec}",
                            }
                        )
                        continue

                    coalesce_bytes.extend(bytes(audio_bytes))
                    coalesce_sample_rate = int(packet.get("sample_rate") or 16000)
                    if packet.get("text"):
                        coalesce_text = str(packet.get("text") or "")
                    coalesce_final = coalesce_final or bool(packet.get("is_final_packet"))
                    if coalesce_first_produced_at is None:
                        coalesce_first_produced_at = produced_at
                    if coalesce_tts_first_pcm_at_ms is None:
                        raw_first_pcm_ms = packet.get("tts_first_pcm_at_ms")
                        if isinstance(raw_first_pcm_ms, int) and raw_first_pcm_ms > 0:
                            coalesce_tts_first_pcm_at_ms = int(raw_first_pcm_ms)
                    if coalesce_deadline <= 0:
                        coalesce_deadline = now + 0.02

                    should_flush = (
                        len(coalesce_bytes) >= coalesce_target_bytes or coalesce_final or packet_latency_ms > 120
                    )
                    if not should_flush:
                        continue

                    if (time.perf_counter() - candidate_last_spoken_at) < 0.6:
                        interrupt_generation += 1
                        local_interrupt_generation = interrupt_generation
                        _clear_packet_queue()
                        _reset_coalesce_state()
                        continue
                    await _flush(now)
                except asyncio.TimeoutError:
                    if coalesce_bytes and coalesce_deadline > 0 and time.perf_counter() >= coalesce_deadline:
                        await _flush(time.perf_counter())
                    continue
        except asyncio.CancelledError:
            return
        except Exception as exc:
            if not websocket_closed:
                logger.error("TTS dispatcher error: %s", exc)

    async def _run_asr_queue_consumer() -> None:
        nonlocal latest_received_seq, last_flushed_seq
        try:
            while not websocket_closed:
                try:
                    message, audio_bytes, recv_start = await asyncio.wait_for(audio_chunk_queue.get(), timeout=0.6)
                except asyncio.TimeoutError:
                    if latest_received_seq > last_flushed_seq:
                        await asyncio.to_thread(_safe_flush_asr, latest_received_seq)
                    continue

                frame_id = str(message.get("frame_id") or "")
                seq = int(message.get("seq") or 0)
                if seq > 0:
                    latest_received_seq = seq

                try:
                    chunk_index = int(message.get("chunk_index") or 1)
                    chunk_total = int(message.get("chunk_total") or 1)
                    is_final = bool(message.get("is_final"))

                    def _run_process() -> dict[str, Any] | Any:
                        from ...db.session import SessionLocal

                        with SessionLocal() as local_session:
                            local_service = get_ai_interview_service(local_session)
                            return local_service.process_duplex_audio_chunk(
                                session_id=session_id,
                                seq=seq,
                                chunk_index=chunk_index,
                                chunk_total=chunk_total,
                                is_final=is_final,
                                payload=message,
                                audio_bytes=audio_bytes,
                            )

                    result = await asyncio.to_thread(_run_process)
                    asr_part = result.get("asr") if isinstance(result, dict) else None
                    if isinstance(asr_part, dict):
                        breakdown = asr_part.get("latency_breakdown")
                        if isinstance(breakdown, dict) and isinstance(breakdown.get("asr_ms"), int):
                            asr_latencies_ms.append(int(breakdown["asr_ms"]))
                        elif isinstance(asr_part.get("latency_ms"), int):
                            asr_latencies_ms.append(int(asr_part["latency_ms"]))
                    e2e_latencies_ms.append(max(1, int((time.perf_counter() - recv_start) * 1000)))
                    await _safe_send({"type": "duplex.turn", "data": result})
                    if is_final:
                        transcript = str((asr_part or {}).get("transcript") or "").strip()
                        provider = str((asr_part or {}).get("provider") or "")
                        logger.info(
                            "[FinalDiag][WS Processed] session=%s frame_id=%s seq=%s chunk=%s/%s provider=%s transcript_len=%s",
                            session_id,
                            frame_id,
                            seq,
                            chunk_index,
                            chunk_total,
                            provider,
                            len(transcript),
                        )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error("Error processing duplex chunk %s: %s", frame_id, exc)
                    await _safe_send(
                        {
                            "type": "duplex.error",
                            "session_id": session_id,
                            "error": "chunk_processing_failed",
                            "frame_id": frame_id,
                            "detail": str(exc),
                        }
                    )
                finally:
                    audio_chunk_queue.task_done()
        except asyncio.CancelledError:
            return
        except Exception as exc:
            if not websocket_closed:
                logger.error("Audio queue consumer error: %s", exc)

    async def _lifecycle_start() -> None:
        nonlocal event_sub, listener_task, dispatcher_task, audio_consumer_task
        await websocket.accept()
        logger.info("ai_interview.ws.duplex_open trace_id=%s session_id=%s", session_id, session_id)
        await _safe_send({"type": "duplex.connected", "session_id": session_id})
        DEFAULT_INTERVIEW_EVENT_BUS.bind_loop(asyncio.get_running_loop())
        event_sub = DEFAULT_INTERVIEW_EVENT_BUS.subscribe(session_id=session_id)
        try:
            await asyncio.to_thread(service.asr_warmup, session_id=session_id)
            await asyncio.to_thread(service.tts_warmup, session_id=session_id, voice="default")
        except Exception as warmup_exc:
            logger.warning("Initial warmup failed for %s: %s", session_id, warmup_exc)
        listener_task = asyncio.create_task(_run_event_bus_listener(), name=f"duplex-listener-{session_id}")
        dispatcher_task = asyncio.create_task(_run_tts_dispatcher(), name=f"duplex-dispatcher-{session_id}")
        audio_consumer_task = asyncio.create_task(_run_asr_queue_consumer(), name=f"duplex-audio-consumer-{session_id}")

    async def _lifecycle_stop() -> None:
        nonlocal websocket_closed
        if (accepted_count or duplicate_count or server_drop_count) and not websocket_closed:
            try:
                await _emit_stats()
            except Exception:
                pass

        websocket_closed = True
        if event_sub is not None:
            DEFAULT_INTERVIEW_EVENT_BUS.unsubscribe(event_sub)
        if pending_finalize_task and not pending_finalize_task.done():
            pending_finalize_task.cancel()
            try:
                await asyncio.wait({pending_finalize_task}, timeout=1.0)
            except Exception:
                pass
        cleanup_tasks = [t for t in (audio_consumer_task, listener_task, dispatcher_task) if t is not None]
        for task in cleanup_tasks:
            if not task.done():
                task.cancel()
        if cleanup_tasks:
            try:
                await asyncio.wait(cleanup_tasks, timeout=2.0)
            except Exception:
                pass
    async def _handle_end_of_turn(message: dict[str, Any], recv_start: float) -> None:
        eot_seq = int(message.get("seq") or 0)
        eot_frame_id = str(message.get("frame_id") or "").strip()
        if eot_seq <= 0:
            await _safe_send({"type": "duplex.error", "error": "invalid_eot_seq"})
            return
        ack_latency_ms = max(1, int((time.perf_counter() - recv_start) * 1000))
        await _safe_send(
            {
                "type": "duplex.eot_ack",
                "session_id": session_id,
                "frame_id": eot_frame_id,
                "seq": eot_seq,
                "status": "accepted",
                "ack_latency_ms": ack_latency_ms,
            }
        )
        logger.info("[FinalDiag][WS EOT] accepted session=%s frame_id=%s seq=%s", session_id, eot_frame_id, eot_seq)
        try:
            def _run_eot() -> Any:
                from ...db.session import SessionLocal

                with SessionLocal() as local_session:
                    local_service = get_ai_interview_service(local_session)
                    return local_service.process_duplex_end_of_turn(session_id=session_id, seq=eot_seq, payload=message)

            eot_result = await asyncio.to_thread(_run_eot)
            await _safe_send({"type": "duplex.turn", "data": eot_result})
        except Exception as exc:
            logger.error("Error processing end_of_turn: session=%s seq=%s err=%s", session_id, eot_seq, exc)
            await _safe_send(
                {
                    "type": "duplex.error",
                    "session_id": session_id,
                    "error": "eot_processing_failed",
                    "frame_id": eot_frame_id,
                    "detail": str(exc),
                }
            )

    async def _handle_client_playback_mark(message: dict[str, Any], recv_start: float) -> None:
        playback_seq = int(message.get("seq") or 0)
        if playback_seq <= 0:
            await _safe_send({"type": "duplex.error", "error": "invalid_playback_seq"})
            return
        packet_idx = int(message.get("packet_index") or 0)
        client_ts_raw = message.get("client_ts_ms")
        client_ts_ms = int(client_ts_raw) if isinstance(client_ts_raw, (int, float)) else None
        ack_latency_ms = max(1, int((time.perf_counter() - recv_start) * 1000))
        await _safe_send(
            {
                "type": "duplex.client_playback_ack",
                "session_id": session_id,
                "seq": playback_seq,
                "packet_index": packet_idx,
                "status": "accepted",
                "ack_latency_ms": ack_latency_ms,
            }
        )

        def _run_mark() -> Any:
            from ...db.session import SessionLocal

            with SessionLocal() as local_session:
                local_service = get_ai_interview_service(local_session)
                return local_service.record_client_playback_mark(
                    session_id=session_id,
                    seq=playback_seq,
                    packet_index=packet_idx if packet_idx > 0 else None,
                    client_ts_ms=client_ts_ms,
                    transport=str(message.get("transport") or "binary"),
                )

        asyncio.create_task(asyncio.to_thread(_run_mark), name=f"duplex-playback-mark-{session_id}-{playback_seq}")

    await _lifecycle_start()
    try:
        while True:
            raw_msg = await websocket.receive()
            if raw_msg.get("type") == "websocket.disconnect":
                break

            recv_start = time.perf_counter()
            decoded = _decode_inbound(raw_msg)
            if decoded is None:
                break
            message, audio_bytes = decoded
            if not message:
                continue

            msg_type = str(message.get("type") or "").strip().lower()
            if msg_type == "ping":
                await _safe_send({"type": "pong", "session_id": session_id})
                continue
            if msg_type == "end_of_turn":
                await _handle_end_of_turn(message, recv_start)
                continue
            if msg_type == "client_playback_mark":
                await _handle_client_playback_mark(message, recv_start)
                continue
            if msg_type != "audio_chunk":
                await _safe_send({"type": "duplex.error", "error": "unsupported_message_type"})
                continue

            received_audio_chunks += 1
            frame_id = str(message.get("frame_id") or "").strip()
            if not frame_id:
                await _safe_send({"type": "duplex.error", "error": "missing_frame_id"})
                continue

            ack_latency_ms = max(1, int((time.perf_counter() - recv_start) * 1000))

            if frame_id in seen_frame_ids:
                duplicate_count += 1
                ack_latencies_ms.append(ack_latency_ms)
                await _safe_send(
                    {
                        "type": "duplex.ack",
                        "session_id": session_id,
                        "frame_id": frame_id,
                        "status": "duplicate",
                        "ack_latency_ms": ack_latency_ms,
                    }
                )
                await _emit_stats_if_needed()
                continue

            if audio_chunk_queue.full():
                server_drop_count += 1
                await _safe_send(
                    {
                        "type": "duplex.error",
                        "session_id": session_id,
                        "error": "server_busy",
                        "frame_id": frame_id,
                        "retryable": True,
                    }
                )
                await _emit_stats_if_needed()
                continue

            _remember_frame_id(frame_id)
            accepted_count += 1
            ack_latencies_ms.append(ack_latency_ms)
            await _safe_send(
                {
                    "type": "duplex.ack",
                    "session_id": session_id,
                    "frame_id": frame_id,
                    "status": "accepted",
                    "ack_latency_ms": ack_latency_ms,
                }
            )
            await _emit_stats_if_needed()

            await audio_chunk_queue.put((message, audio_bytes, recv_start))
    except WebSocketDisconnect:
        return
    finally:
        await _lifecycle_stop()
