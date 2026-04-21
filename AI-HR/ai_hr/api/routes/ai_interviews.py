"""AI interview routes."""

from __future__ import annotations

import asyncio
import logging
import concurrent.futures
import json
import threading
import time
import uuid
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy.orm import Session
from ...core.responses import Envelope
from ...core.security import require_ai_interview_auth, require_ai_interview_ws_auth
from ...db.session import get_db_session
from ...core.config import get_settings
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
    accepted = 0
    for item in payload.events:
        event_session_id = str(item.session_id or session_id).strip()
        if event_session_id != session_id:
            continue
        DEFAULT_INTERVIEW_EVENT_BUS.publish(
            session_id=session_id,
            event_type=str(item.event_type or "").strip(),
            payload={
                **dict(item.payload or {}),
                "event_id": item.event_id,
                "source": item.source or "ten_agent",
                "bridge_ts": item.ts,
            },
        )
        accepted += 1
    return Envelope.success({"accepted": accepted})


@router.post("/sessions/{session_id}/question-set/generate", response_model=Envelope[AIInterviewQuestionGenerateResult])
def generate_ai_interview_question_set(
    session_id: str,
    payload: AIInterviewQuestionGenerateRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[AIInterviewQuestionGenerateResult]:
    """Route handler."""
    service = get_ai_interview_service(session)
    result = service.generate_question_set(session_id, payload)
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

    # --- WebSocket session state & task handles ---
    from collections import deque
    websocket_closed = False
    send_lock = asyncio.Lock()
    event_sub = None
    audio_consumer_task = None
    listener_task = None
    dispatcher_task = None

    
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

    audio_chunk_queue: asyncio.Queue[tuple[tuple[dict, bytes | None], float]] = asyncio.Queue(maxsize=128)
    
    service = get_ai_interview_service(session)
    await websocket.accept()
    logger.info("ai_interview.ws.duplex_open trace_id=%s session_id=%s", session_id, session_id)
    await websocket.send_json({"type": "duplex.connected", "session_id": session_id})
    
    # CRITICAL: Bind the event bus to the current running loop for async distribution
    from ai_hr.services.orchestrator.event_bus import DEFAULT_INTERVIEW_EVENT_BUS
    DEFAULT_INTERVIEW_EVENT_BUS.bind_loop(asyncio.get_running_loop())
    
    # Pre-warm ASR/TTS connection for the duplex session asynchronously to avoid blocking initialization
    try:
        await asyncio.to_thread(service.asr_warmup, session_id=session_id)
        await asyncio.to_thread(service.tts_warmup, session_id=session_id, voice="default")
    except Exception as e:
        logger.warning(f"Initial warmup failed for {session_id}: {e}")

    def _percentile(values: list[int], p: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        rank = max(1, min(len(ordered), int(len(ordered) * p + 0.9999)))
        return float(ordered[rank - 1])

    def _latency_summary(values: list[int]) -> dict:
        return {
            "p50": _percentile(values, 0.50),
            "p95": _percentile(values, 0.95),
            "p99": _percentile(values, 0.99),
            "samples": len(values),
        }

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

    async def _safe_send(payload: dict) -> bool:
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

    def _remember_frame_id(frame_id: str) -> None:
        seen_frame_ids.add(frame_id)
        seen_frame_queue.append(frame_id)
        while len(seen_frame_queue) > max_seen_frames:
            old_frame_id = seen_frame_queue.popleft()
            seen_frame_ids.discard(old_frame_id)

    async def _handle_chunk(message: dict, chunk_start: float) -> None:
        def _run_ingest():
            from ...db.session import SessionLocal
            with SessionLocal() as local_session:
                local_service = get_ai_interview_service(local_session)
                return local_service.process_duplex_audio_chunk(session_id=session_id, payload=message)
        
        result = await asyncio.to_thread(_run_ingest)
        asr_data = result.get("asr") if isinstance(result, dict) else None
        if isinstance(asr_data, dict):
            latency_breakdown = asr_data.get("latency_breakdown")
            if isinstance(latency_breakdown, dict) and isinstance(latency_breakdown.get("asr_ms"), int):
                asr_latencies_ms.append(int(latency_breakdown["asr_ms"]))
            elif isinstance(asr_data.get("latency_ms"), int):
                asr_latencies_ms.append(int(asr_data["latency_ms"]))
        await _safe_send({"type": "duplex.turn", "data": result})

        event_data = result.get("event") if isinstance(result, dict) else None
        if isinstance(event_data, dict):
            # We now handle TTS incrementally via the event bus
            # instead of waiting for followup_question here.
            pass

    # --- Session-wide TTS Streaming Infrastructure (Phase 1) ---
    packet_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=512)
    event_sub = DEFAULT_INTERVIEW_EVENT_BUS.subscribe(session_id=session_id)
    interrupt_generation = 0
    candidate_last_spoken_at = 0.0
    active_generation_id = 0  # Monotonically increasing ID to invalidate stale LLM tasks
    pending_finalize_task: asyncio.Task | None = None

    def _clear_packet_queue() -> None:
        while True:
            try:
                packet_queue.get_nowait()
                packet_queue.task_done()
            except asyncio.QueueEmpty:
                break

    async def _listen_event_bus():
        nonlocal interrupt_generation, candidate_last_spoken_at, active_generation_id, pending_finalize_task
        try:
            while not websocket_closed:
                try:
                    event = await asyncio.wait_for(event_sub.queue.get(), timeout=1.0)

                    if event.get("event_type") == "asr.turn":
                        candidate_last_spoken_at = time.perf_counter()

                        active_generation_id += 1
                        local_gen_id = active_generation_id


                        if pending_finalize_task and not pending_finalize_task.done():
                            pending_finalize_task.cancel()
                        
                        payload = event.get("payload", {})
                        if payload:
                            await _safe_send({"type": "duplex.asr.turn", "data": payload})
                            # Bridge to service layer if this is a final turn to trigger LLM
                            seq = payload.get("seq")
                            is_final = bool(payload.get("is_final"))
                            
                            if is_final:
                                transcript = str(payload.get("transcript") or "").strip()
                                # Pre-check semantics to decide if we should debounce
                                from ai_hr.services.interview_runtime.semantic_endpoint import evaluate_semantic_floor
                                # Note: we don't know the exact stage here easily, default to S2/S3 cautious mode
                                floor_action = evaluate_semantic_floor(transcript, stage="S3")
                                
                                async def _debounced_trigger(target_gen_id: int):
                                    if floor_action == "HOLD":
                                        # Human pause or unfinished sentence: wait longer
                                        await asyncio.sleep(1.0)
                                    else:
                                        # Likely finished, but still add a tiny debounce to catch fragmented ASR
                                        await asyncio.sleep(0.3)
                                    
                                    # Final check before triggering: has user spoken again?
                                    if active_generation_id != target_gen_id:
                                        return

                                    def _trigger_append():
                                        try:
                                            # Check again inside the thread (as best as possible)
                                            if active_generation_id != target_gen_id:
                                                return

                                            from ...db.session import SessionLocal
                                            from ...schemas.ai_interviews import AIInterviewSessionEventRequest
                                            with SessionLocal() as local_session:
                                                local_service = get_ai_interview_service(local_session)
                                                event_req = AIInterviewSessionEventRequest(
                                                    event_id=str(payload.get("event_id") or uuid.uuid4().hex),
                                                    seq=max(1, int(seq or 1)),
                                                    speaker="candidate",
                                                    transcript=transcript,
                                                    confidence=float(payload.get("confidence") or 0.9),
                                                    payload=payload,
                                                )
                                                
                                                # Perform the actual heavy lifting (LLM call etc)
                                                res = local_service.append_event(session_id, event_req)
                                                
                                                # Post-generation check: if user started talking while we were in the LLM,
                                                # we MUST NOT allow any side effects (though DB already updated).
                                                # The TTS packets produced in the background will be blocked by Gatekeeper/interrupt_generation.
                                                return res
                                        except Exception as bridge_exc:
                                            if not isinstance(bridge_exc, asyncio.CancelledError):
                                                logger.exception(
                                                    "ai_interview.ws.bridge_thread_error trace_id=%s session_id=%s",
                                                    session_id,
                                                    session_id,
                                                )
                                    
                                    # Run the actual trigger
                                    await asyncio.to_thread(_trigger_append)

                                pending_finalize_task = asyncio.create_task(_debounced_trigger(local_gen_id))
                    elif event.get("event_type") == "tts.packet":
                        payload = event.get("payload", {})
                        if not packet_queue.full():
                            packet_to_dispatch = dict(payload)
                            packet_to_dispatch["produced_at"] = time.perf_counter()
                            await packet_queue.put(packet_to_dispatch)
                    elif event.get("event_type") == "llm.sentence":
                        payload = event.get("payload", {})
                        if payload:
                            await _safe_send({"type": "duplex.llm.sentence", "data": payload})
                    elif event.get("event_type") == "tts.interrupt":
                        interrupt_generation += 1
                        _clear_packet_queue()
                        await _safe_send({"type": "duplex.tts.interrupt", "session_id": session_id})
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            if not websocket_closed:
                logger.error(f"Event bus listener error: {exc}")

    last_interaction_time = time.perf_counter()
    latest_received_seq = 0
    last_flushed_seq = 0
    
    def _safe_flush_asr(seq: int):
        nonlocal last_flushed_seq
        if seq <= last_flushed_seq:
            return
        last_flushed_seq = seq
        # logger.debug(f"DEBUG [Backend VAD] Triggering flush for session={session_id} seq={seq}")
        from ...db.session import SessionLocal
        with SessionLocal() as local_session:
            local_service = get_ai_interview_service(local_session)
            local_service.process_duplex_end_of_turn(session_id=session_id, seq=seq, payload={"source": "backend_vad"})

    async def _dispatch_packets_session():
        """Route handler."""
        nonlocal interrupt_generation
        packet_index = 0
        prev_sent_at: float | None = None
        coalesce_bytes = bytearray()
        coalesce_sample_rate = 16000
        coalesce_text = ""
        coalesce_final = False
        coalesce_deadline = 0.0
        coalesce_first_produced_at: float | None = None
        coalesce_tts_first_pcm_at_ms: int | None = None
        coalesce_target_bytes = int(16000 * 2 * 0.02)
        local_interrupt_generation = interrupt_generation

        async def _flush_coalesced(now: float) -> None:
            nonlocal packet_index, prev_sent_at, coalesce_bytes, coalesce_sample_rate, coalesce_text, coalesce_final, coalesce_deadline, coalesce_first_produced_at, coalesce_tts_first_pcm_at_ms
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
            await _safe_send({
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
            })
            await _safe_send_bytes(bytes(coalesce_bytes))
            coalesce_bytes = bytearray()
            coalesce_text = ""
            coalesce_final = False
            coalesce_deadline = 0.0
            coalesce_first_produced_at = None
            coalesce_tts_first_pcm_at_ms = None

        try:
            while not websocket_closed:
                try:
                    if local_interrupt_generation != interrupt_generation:
                        coalesce_bytes = bytearray()
                        coalesce_text = ""
                        coalesce_final = False
                        coalesce_deadline = 0.0
                        coalesce_first_produced_at = None
                        coalesce_tts_first_pcm_at_ms = None
                        local_interrupt_generation = interrupt_generation

                    wait_timeout = 0.02
                    if coalesce_bytes and coalesce_deadline > 0:
                        wait_timeout = max(0.005, min(wait_timeout, coalesce_deadline - time.perf_counter()))
                    packet = await asyncio.wait_for(packet_queue.get(), timeout=wait_timeout)
                    if packet.get("_error"):
                        await _safe_send({"type": "duplex.error", "error": "tts_stream_failed", "detail": packet.get("_error")})
                        continue

                    now = time.perf_counter()
                    produced_at = float(packet.get("produced_at") or now)
                    packet_latency_ms = max(0, int((now - produced_at) * 1000))

                    audio_bytes = packet.get("audio_bytes")
                    use_binary = bool(isinstance(audio_bytes, (bytes, bytearray)) and len(audio_bytes) > 0)
                    if not use_binary:
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
                    coalesce_final = coalesce_final or bool(packet.get("is_final_packet", False))
                    if coalesce_first_produced_at is None:
                        coalesce_first_produced_at = produced_at
                    if coalesce_tts_first_pcm_at_ms is None:
                        raw_tts_first_pcm_at_ms = packet.get("tts_first_pcm_at_ms")
                        if isinstance(raw_tts_first_pcm_at_ms, int) and raw_tts_first_pcm_at_ms > 0:
                            coalesce_tts_first_pcm_at_ms = int(raw_tts_first_pcm_at_ms)
                    if coalesce_deadline <= 0:
                        coalesce_deadline = now + 0.02

                    should_flush = (
                        len(coalesce_bytes) >= coalesce_target_bytes
                        or coalesce_final
                        or packet_latency_ms > 120
                    )
                    if should_flush:
                        time_since_speech = time.perf_counter() - candidate_last_spoken_at
                        if time_since_speech < 0.6:
                            logger.info(f"[Gatekeeper] TTS transmission aborted because candidate is speaking (gap: {time_since_speech:.3f}s)")
                            interrupt_generation += 1
                            local_interrupt_generation = interrupt_generation
                            _clear_packet_queue()
                            coalesce_bytes = bytearray()
                            coalesce_text = ""
                            coalesce_final = False
                            coalesce_deadline = 0.0
                            coalesce_first_produced_at = None
                            coalesce_tts_first_pcm_at_ms = None
                        else:
                            await _flush_coalesced(now)
                except asyncio.TimeoutError:
                    if coalesce_bytes and coalesce_deadline > 0 and time.perf_counter() >= coalesce_deadline:
                        await _flush_coalesced(time.perf_counter())
                    continue
        except Exception as exc:
            if not websocket_closed:
                logger.error(f"TTS Dispatcher error: {exc}")

    # Start session-wide background workers
    listener_task = asyncio.create_task(_listen_event_bus(), name=f"duplex-listener-{session_id}")
    dispatcher_task = asyncio.create_task(_dispatch_packets_session(), name=f"duplex-dispatcher-{session_id}")


    async def _handle_chunk_with_guard(payload: dict, frame_id: str, recv_start: float, audio_bytes: bytes | None = None) -> None:
        try:
            chunk_index = int(payload.get("chunk_index") or 1)
            chunk_total = int(payload.get("chunk_total") or 1)
            is_final = bool(payload.get("is_final", False))
            
            def _run_sync_process():
                # We must use a local DB session here because this runs in a thread
                from ...db.session import SessionLocal
                with SessionLocal() as local_session:
                    local_service = get_ai_interview_service(local_session)
                    return local_service.process_duplex_audio_chunk(
                        session_id=session_id,
                        seq=int(payload.get("seq") or 0),
                        chunk_index=chunk_index,
                        chunk_total=chunk_total,
                        is_final=is_final,
                        payload=payload,
                        audio_bytes=audio_bytes,
                    )
            
            result = await asyncio.to_thread(_run_sync_process)
            if is_final:
                asr_part = (result or {}).get("asr") if isinstance(result, dict) else {}
                event_part = (result or {}).get("event") if isinstance(result, dict) else None
                transcript = str((asr_part or {}).get("transcript") or "").strip()
                provider = str((asr_part or {}).get("provider") or "")
                logger.info(
                    "[FinalDiag][WS Processed] session=%s frame_id=%s seq=%s chunk=%s/%s is_final=%s provider=%s transcript_len=%s has_event=%s",
                    session_id,
                    frame_id,
                    payload.get("seq"),
                    chunk_index,
                    chunk_total,
                    is_final,
                    provider,
                    len(transcript),
                    bool(event_part),
                )
            e2e_latencies_ms.append(max(1, int((time.perf_counter() - recv_start) * 1000)))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(f"Error processing duplex chunk {frame_id}: {exc}")
            await _safe_send({
                "type": "duplex.error",
                "session_id": session_id,
                "error": "chunk_processing_failed",
                "frame_id": frame_id,
                "detail": str(exc),
            })

    async def _audio_queue_consumer():
        """Route handler."""
        nonlocal latest_received_seq, last_flushed_seq
        try:
            while not websocket_closed:
                try:
                    item, chunk_start = await asyncio.wait_for(audio_chunk_queue.get(), timeout=0.6)
                    message, audio_bytes = item
                    frame_id = str(message.get("frame_id") or "")
                    
                    seq = int(message.get("seq") or 0)
                    if seq > 0:
                        latest_received_seq = seq
                    
                    await _handle_chunk_with_guard(message, frame_id, chunk_start, audio_bytes=audio_bytes)
                    audio_chunk_queue.task_done()
                except asyncio.TimeoutError:
                    if latest_received_seq > last_flushed_seq:
                        # logger.debug(f"DEBUG [Backend VAD] Silence detected (>600ms), flushing seq={latest_received_seq}")
                        await asyncio.to_thread(_safe_flush_asr, latest_received_seq)
                    continue
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            if not websocket_closed:
                logger.error(f"Audio queue consumer error: {exc}")

    # Start session-wide background workers
    audio_consumer_task = asyncio.create_task(_audio_queue_consumer(), name=f"duplex-audio-consumer-{session_id}")

    try:
        while True:
            raw_msg = await websocket.receive()
            if raw_msg["type"] == "websocket.disconnect":
                break
            
            recv_start = time.perf_counter()
            message: dict = {}
            audio_bytes: bytes | None = None
            
            if "text" in raw_msg:
                try:
                    message = json.loads(raw_msg["text"])
                except Exception: continue
            elif "bytes" in raw_msg:
                # Binary Frame: [2 bytes JSON size][JSON][PCM]
                bdata = raw_msg["bytes"]
                if len(bdata) < 2: continue
                jlen = int.from_bytes(bdata[:2], "big")
                try:
                    message = json.loads(bdata[2:2+jlen].decode("utf-8"))
                    audio_bytes = bdata[2+jlen:]
                except Exception: continue
            else:
                continue
            
            if received_audio_chunks % 50 == 0:
                logger.debug(f"[WS In] Recv chunk #{received_audio_chunks}, len={len(audio_bytes or '') if audio_bytes else 'text'}")

            msg_type = str(message.get("type") or "").strip().lower()
            if msg_type == "ping":
                await websocket.send_json({"type": "pong", "session_id": session_id})
                continue
            if msg_type == "end_of_turn":
                eot_seq = int(message.get("seq") or 0)
                eot_frame_id = str(message.get("frame_id") or "").strip()
                if eot_seq <= 0:
                    await _safe_send({"type": "duplex.error", "error": "invalid_eot_seq"})
                    continue
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
                logger.info(
                    "[FinalDiag][WS EOT] accepted session=%s frame_id=%s seq=%s",
                    session_id,
                    eot_frame_id,
                    eot_seq,
                )
                logger.info(f"DEBUG [WS EndOfTurn] 用户已停止说话: session={session_id} seq={eot_seq}")
                try:
                    def _run_eot():
                        from ...db.session import SessionLocal
                        with SessionLocal() as local_session:
                            local_service = get_ai_interview_service(local_session)
                            return local_service.process_duplex_end_of_turn(
                                session_id=session_id,
                                seq=eot_seq,
                                payload=message,
                            )

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
                continue
            if msg_type == "client_playback_mark":
                playback_seq = int(message.get("seq") or 0)
                if playback_seq <= 0:
                    await _safe_send({"type": "duplex.error", "error": "invalid_playback_seq"})
                    continue
                packet_idx = int(message.get("packet_index") or 0)
                client_ts_ms_raw = message.get("client_ts_ms")
                client_ts_ms = int(client_ts_ms_raw) if isinstance(client_ts_ms_raw, (int, float)) else None
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
                try:
                    def _run_playback_mark():
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

                    asyncio.create_task(asyncio.to_thread(_run_playback_mark))
                except Exception as playback_exc:
                    logger.error("Error recording client playback mark: session=%s seq=%s err=%s", session_id, playback_seq, playback_exc)
                continue
            if msg_type != "audio_chunk":
                await websocket.send_json({"type": "duplex.error", "error": "unsupported_message_type"})
                continue
            received_audio_chunks += 1

            frame_id = str(message.get("frame_id") or "").strip()
            if not frame_id:
                await _safe_send({"type": "duplex.error", "error": "missing_frame_id"})
                continue
            if frame_id in seen_frame_ids:
                duplicate_count += 1
                ack_latency_ms = max(1, int((time.perf_counter() - recv_start) * 1000))
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
                if bool(message.get("is_final", False)):
                    logger.warning(
                        "[FinalDiag][WS Duplicate] final frame duplicate session=%s frame_id=%s seq=%s chunk_index=%s",
                        session_id,
                        frame_id,
                        message.get("seq"),
                        message.get("chunk_index"),
                    )
                if (accepted_count + duplicate_count + server_drop_count) % stats_emit_every == 0:
                    await _emit_stats()
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
                if bool(message.get("is_final", False)):
                    logger.error(
                        "[FinalDiag][WS Drop] final frame dropped by server_busy session=%s frame_id=%s seq=%s chunk_index=%s",
                        session_id,
                        frame_id,
                        message.get("seq"),
                        message.get("chunk_index"),
                    )
                if (accepted_count + duplicate_count + server_drop_count) % stats_emit_every == 0:
                    await _emit_stats()
                continue

            _remember_frame_id(frame_id)
            accepted_count += 1
            ack_latency_ms = max(1, int((time.perf_counter() - recv_start) * 1000))
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
            if bool(message.get("is_final", False)):
                logger.info(
                    "[FinalDiag][WS Ack] accepted final frame session=%s frame_id=%s seq=%s chunk_index=%s audio_len=%s",
                    session_id,
                    frame_id,
                    message.get("seq"),
                    message.get("chunk_index"),
                    len(audio_bytes or b""),
                )
            if (accepted_count + duplicate_count + server_drop_count) % stats_emit_every == 0:
                await _emit_stats()
            
            chunk_start = time.perf_counter()
            await audio_chunk_queue.put(((message, audio_bytes), chunk_start))
    except WebSocketDisconnect:
        websocket_closed = True
        return
    finally:
        # Stop further activity first
        websocket_closed = True
        if event_sub:
            DEFAULT_INTERVIEW_EVENT_BUS.unsubscribe(event_sub)
        
        # Cleanup session tasks explicitly
        all_to_cleanup = [t for t in [audio_consumer_task, listener_task, dispatcher_task] if t is not None]
        for task in all_to_cleanup:
            if not task.done():
                task.cancel()
        
        # Await all tasks to finish cancellation to avoid "destroyed while pending"
        if all_to_cleanup:
            # We must use a timeout or protective gather to ensure we don't hang finally forever
            try:
                await asyncio.wait(all_to_cleanup, timeout=2.0)
            except Exception:
                pass

        if (accepted_count or duplicate_count or server_drop_count):
            try:
                await _emit_stats()
            except Exception:
                pass

