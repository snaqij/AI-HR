"""AI 面试会话服务。"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
import uuid

# ── 进程级 Provider 单例（双检锁）──
# AliyunNlsASRProvider 维护 NLS WebSocket 长连接，必须全局复用。
# 每次调用 get_ai_interview_service 若重新 create_asr_provider，
# 会为每个音频 chunk 新建连接，立即触发 TOO_MANY_REQUESTS。
_PROVIDER_SINGLETON_LOCK = threading.Lock()
_ASR_PROVIDER_SINGLETON: "ASRProvider | None" = None
_TTS_PROVIDER_SINGLETON: "TTSProvider | None" = None

# Turn-level deduplication markers for duplex flow
_DUPLEX_FINALIZE_LOCK = threading.Lock()
_DUPLEX_FINALIZED_SEQ: dict[str, set[int]] = {}
from sqlalchemy.orm import Session
from ..core.config import get_settings
from ..core.exceptions import InvalidStateError
from ..db.session import SessionLocal
from ..repositories.ai_interviews import AIInterviewSessionRepository
from ..repositories.ai_observability import AIObservabilityRepository
from ..repositories.ai_runtime import AIRuntimeRepository
from ..repositories.candidates import CandidateRepository
from ..repositories.events import EventRepository
from ..repositories.interviews import InterviewRepository
from ..repositories.jobs import JobRepository
from .rtc.base import RTCGateway
from .rtc.factory import create_rtc_gateway
from .speech.base import ASRProvider, TTSProvider
from .speech.factory import create_asr_provider, create_tts_provider
from .llm.client import InvokeContext, LLMClient
from .llm.guardrails import GuardrailService
from .llm.prompts import PromptTemplate, get_prompt_template
from .llm.router import ModelRouter
from .orchestrator.realtime import RealtimeOrchestrator
from .orchestrator.event_bus import DEFAULT_INTERVIEW_EVENT_BUS
from .interview_runtime.factory import get_interview_runtime_store
from .interview_runtime.question_flow import InterviewQuestionFlowEngine
from .interview_runtime.store import InterviewRuntimeStore
from ..schemas.ai_interviews import (
    AIInterviewASRStreamRequest,
    AIInterviewASRStreamResponse,
    AIInterviewMetricsResponse,
    AIInterviewQuestionGenerateRequest,
    AIInterviewQuestionPackPrebuildRequest,
    AIInterviewRTCAudioSubscribeRequest,
    AIInterviewRTCAudioSubscribeResponse,
    AIInterviewRTCASRIngestRequest,
    AIInterviewRTCVideoPolicyRequest,
    AIInterviewRTCVideoPolicyResponse,
    AIInterviewRTCJoinRequest,
    AIInterviewRTCJoinResponse,
    AIInterviewRTCReconnectRequest,
    AIInterviewRTCReconnectResponse,
    AIInterviewReplayResponse,
    AIInterviewReportResponse,
    AIInterviewSessionCreateRequest,
    AIInterviewSessionEventRequest,
    AIInterviewSessionFinishRequest,
    AIInterviewSessionHandoffRequest,
    AIInterviewSessionStartRequest,
    AIInterviewTTSStreamRequest,
    AIInterviewTTSStreamResponse,
)

logger = logging.getLogger(__name__)


class AIInterviewService:
    """提供 AI 面试会话编排能力。"""

    def __init__(
        self,
        *,
        session_repository: AIInterviewSessionRepository,
        runtime_repository: AIRuntimeRepository,
        candidate_repository: CandidateRepository,
        job_repository: JobRepository,
        interview_repository: InterviewRepository,
        event_repository: EventRepository,
        rtc_gateway: RTCGateway,
        asr_provider: ASRProvider,
        tts_provider: TTSProvider,
        llm_client: LLMClient,
        orchestrator: RealtimeOrchestrator,
        runtime_store: InterviewRuntimeStore,
    ):
        self._settings = get_settings()
        self._session_repository = session_repository
        self._runtime_repository = runtime_repository
        self._candidate_repository = candidate_repository
        self._job_repository = job_repository
        self._interview_repository = interview_repository
        self._event_repository = event_repository
        self._rtc_gateway = rtc_gateway
        self._asr_provider = asr_provider
        self._tts_provider = tts_provider
        self._llm_client = llm_client
        self._llm_prefetch_client = LLMClient(
            router=ModelRouter(runtime_repository=None, settings=self._settings),
            guardrail_service=GuardrailService(),
            observability_repository=None,
        )
        self._orchestrator = orchestrator
        self._runtime_store = runtime_store
        self._question_flow_engine = InterviewQuestionFlowEngine()
        self._duplex_prefetch_lock = threading.Lock()
        self._duplex_prefetch_cache: dict[str, dict] = {}
        self._duplex_prefetch_inflight: set[str] = set()
        self._duplex_prefetch_abort_events: dict[str, threading.Event] = {}

    def create_session(self, payload: AIInterviewSessionCreateRequest) -> dict:
        """创建 AI 面试会话并返回入会信息。"""
        self._candidate_repository.get(payload.candidate_id)
        self._job_repository.get(payload.job_id)

        join_token = uuid.uuid4().hex
        rtc_room_id = f"ai-intv-{uuid.uuid4()}"
        rtc_info = self._rtc_gateway.create_room(session_id=f"{payload.candidate_id}:{payload.job_id}", preferred_room_id=rtc_room_id)

        entity = self._session_repository.create(
            candidate_id=payload.candidate_id,
            job_id=payload.job_id,
            channel=payload.channel,
            language=payload.language,
            rtc_room_id=rtc_info.room_id,
            join_token=rtc_info.join_token or join_token,
            note=payload.note,
            payload={"interview_stage": "intro", "rtc_vendor": rtc_info.vendor, **dict(payload.payload)},
        )
        return self._to_session_dict(entity)

    def start_session(self, session_id: str, payload: AIInterviewSessionStartRequest) -> dict:
        """启动 AI 面试会话。"""
        entity = self._session_repository.get(session_id)
        if entity.status != "created":
            raise InvalidStateError(f"AI interview session '{session_id}' cannot start from status '{entity.status}'")
        # Prewarm ASR/TTS connection to reduce first-turn latency spikes.
        self.asr_warmup(session_id=session_id)
        self.tts_warmup(session_id=session_id, voice="default")
        
        prebuilt_patch = self._attach_prebuilt_question_pack(session_id=session_id)
        payload_patch = {"last_operator": payload.operator}
        payload_patch.update(prebuilt_patch)
        question_pack = self._runtime_store.get_question_pack(session_id=session_id)
        if question_pack:
            state = self._load_or_init_runtime_state(session_id=session_id, question_pack=question_pack)
            payload_patch["interview_stage"] = self._question_flow_engine.derive_stage(state=state)
        entity = self._session_repository.update_status(
            session_id,
            status="in_progress",
            payload_patch=payload_patch,
        )
        return self._to_session_dict(entity)

    def asr_warmup(self, session_id: str) -> None:
        """预热 ASR 连接。"""
        try:
            self._asr_provider.warmup(session_id=session_id)
        except Exception:
            pass

    def tts_warmup(self, session_id: str, voice: str = "default") -> None:
        """预热 TTS 资源。"""
        try:
            self._tts_provider.warmup(session_id=session_id, voice=voice)
        except Exception:
            pass

    def finish_session(self, session_id: str, payload: AIInterviewSessionFinishRequest) -> dict:
        """结束 AI 面试会话。"""
        entity = self._session_repository.get(session_id)
        if entity.status != "in_progress":
            raise InvalidStateError(f"AI interview session '{session_id}' cannot finish from status '{entity.status}'")
        entity = self._session_repository.update_status(
            session_id,
            status=payload.result_status,
            note=payload.note,
            payload_patch={"finish_operator": payload.operator, "interview_stage": "closing"},
        )
        return self._to_session_dict(entity)

    def handoff_session(self, session_id: str, payload: AIInterviewSessionHandoffRequest) -> dict:
        """将会话转人工并写入 handoff 记录。"""
        entity = self._session_repository.get(session_id)
        if entity.status != "in_progress":
            raise InvalidStateError(f"AI interview session '{session_id}' cannot handoff from status '{entity.status}'")

        handoff = self._session_repository.create_handoff(
            session_id=session_id,
            reason=payload.reason,
            trigger_flags=payload.trigger_flags,
            operator=payload.operator,
            note=payload.note,
            payload=payload.payload,
        )
        entity = self._session_repository.update_status(
            session_id,
            status="failed",
            payload_patch={
                "handoff_id": handoff.id,
                "handoff_reason": payload.reason,
                "handoff_operator": payload.operator,
            },
        )
        return {
            "session": self._to_session_dict(entity),
            "handoff_id": handoff.id,
        }

    def append_event(self, session_id: str, payload: AIInterviewSessionEventRequest) -> dict:
        """上报实时事件并按 event_id 去重。"""
        entity = self._session_repository.get(session_id)
        if entity.status != "in_progress":
            raise InvalidStateError(f"AI interview session '{session_id}' cannot accept events from status '{entity.status}'")

        action: str | None = None
        decision_reason: str | None = None
        decision_flags: list[str] = []
        followup_question: str | None = None
        followup_audio_uris: list[str] = []
        interview_stage: str | None = None
        runtime_mode = self._resolve_runtime_mode()
        model_route = self._resolve_model_route(session_id)
        degradation_mode: str | None = None
        latency_breakdown: dict[str, int] = {}
        effective_transcript = payload.transcript
        effective_confidence = payload.confidence
        
        # 1. Robust Deduplication (Seq-level)
        # Prevents redundant LLM triggers from both ASR Final and EOT Flush for the same turn.
        with _DUPLEX_FINALIZE_LOCK:
            if session_id not in _DUPLEX_FINALIZED_SEQ:
                _DUPLEX_FINALIZED_SEQ[session_id] = set()
            seq_set = _DUPLEX_FINALIZED_SEQ[session_id]
            
            if payload.seq in seq_set:
                logger.info(f"[Deduplication] Session {session_id} Seq {payload.seq} already finalized/processed. Skipping.")
                return {
                    "session_id": session_id,
                    "event_id": payload.event_id,
                    "accepted": False,
                    "deduplicated": True,
                    "turn_id": None,
                    "action": None,
                    "decision_reason": "already_finalized",
                }

            # Only mark as finalized if we are processing a candidate's authoritative turn
            if payload.speaker == "candidate" and (payload.transcript or "").strip():
                # We only mark it as fully 'done' if we are about to trigger the orchestrator
                # Note: seq is added to the set after we are SURE this is a meaningful final turn.
                seq_set.add(payload.seq)

        if self._session_repository.is_event_seen(session_id=session_id, event_id=payload.event_id):
            return {
                "session_id": session_id,
                "event_id": payload.event_id,
                "accepted": False,
                "deduplicated": True,
                "turn_id": None,
                "action": None,
                "decision_reason": None,
                "policy_flags": [],
                "interview_stage": None,
                "followup_question": None,
                "followup_audio_uris": [],
                "runtime_mode": runtime_mode,
                "model_route": model_route,
                "degradation_mode": None,
                "latency_breakdown": {},
            }

        if payload.speaker == "candidate":
            # logger.debug(f"DEBUG [append_event] Processing candidate turn: session={session_id} seq={payload.seq}")
            duplex_mode = bool((payload.payload or {}).get("duplex_mode"))
            prefetched_followup = str((payload.payload or {}).get("prefetched_followup_question") or "").strip()
            prefetched_llm_ms = int((payload.payload or {}).get("prefetched_llm_ms") or 0)
            prefetched_from_partial = bool((payload.payload or {}).get("prefetched_from_partial"))
            
            question_pack = self._runtime_store.get_question_pack(session_id=session_id)
            active_question = self._get_active_question_context(session_id=session_id) if question_pack else None
            active_question_id = None
            if isinstance(active_question, dict):
                raw_qid = active_question.get("id") or active_question.get("index")
                if raw_qid is not None:
                    active_question_id = str(raw_qid)
            
            if question_pack:
                state = self._load_or_init_runtime_state(session_id=session_id, question_pack=question_pack)
                interview_stage = self._advance_stage_by_question_flow(session_id=session_id, state=state)
            else:
                interview_stage = self._advance_stage(session_id)

            def _on_audio_packet(packet: dict) -> None:
                """将 TTS 分片推送至事件总线并打印调试。"""
                DEFAULT_INTERVIEW_EVENT_BUS.publish(
                    session_id=session_id,
                    event_type="tts.packet",
                    payload=packet,
                )

            def llm_stream_wrapper(t, c, s, l):
                return self._build_followup_question_with_llm(
                    session_id=session_id,
                    transcript=t,
                    confidence=c,
                    interview_stage=s,
                    language=l,
                    write_observability=True,
                    abort_event=None,
                    print_stream=True,
                )
            llm_stream_wrapper.is_streaming = True

            orchestrated = self._orchestrator.process_candidate_turn(
                session_id=session_id,
                seq=payload.seq,
                transcript_hint=payload.transcript or "",
                audio_base64=payload.audio_base64,
                confidence=payload.confidence,
                language=entity.language,
                runtime_mode=runtime_mode,
                llm_enabled=self._is_interview_llm_enabled() and not prefetched_followup,
                decide_action=lambda transcript, confidence: self._decide_interview_action(
                    session_id=session_id,
                    transcript=transcript,
                    confidence=confidence,
                ),
                build_rule_followup=lambda transcript, confidence, stage, language, action: self._build_followup_question(
                    transcript=transcript,
                    confidence=confidence,
                    interview_stage=stage,
                    language=language,
                    action=action,
                ),
                build_llm_followup=llm_stream_wrapper,
                interview_stage=interview_stage,
                question_id=active_question_id,
                followup_question=prefetched_followup if prefetched_followup else None,
                tts_enabled=not duplex_mode,
                on_audio_packet=_on_audio_packet,
            )
            effective_transcript = orchestrated.transcript
            action = orchestrated.action
            decision_reason = orchestrated.decision_reason
            decision_flags = orchestrated.policy_flags
            followup_question = orchestrated.followup_question
            followup_audio_uris = orchestrated.followup_audio_uris
            degradation_mode = orchestrated.degradation_mode
            latency_breakdown = orchestrated.latency_breakdown

            if prefetched_followup and action not in {"handoff", "blocked"}:
                followup_question = prefetched_followup
                original_llm_ms = int(latency_breakdown.get("llm_ms") or 0)
                latency_breakdown["llm_ms"] = 0
                latency_breakdown["llm_prefetch_hit"] = 1
                latency_breakdown["llm_prefetch_ms"] = max(0, prefetched_llm_ms)
                latency_breakdown["e2e_ms"] = max(1, int(latency_breakdown.get("e2e_ms") or 0) - original_llm_ms)
                if prefetched_from_partial:
                    decision_flags = [*decision_flags, "llm_prefetch_from_partial"]

            effective_confidence = payload.confidence if payload.confidence is not None else 0.9
            if question_pack and action not in {"handoff", "blocked"}:
                flow_result = self._update_question_flow_after_turn(
                    session_id=session_id,
                    transcript=effective_transcript or "",
                    confidence=effective_confidence,
                    interview_stage=interview_stage,
                    state=state,
                )
                action = flow_result.get("action") or action
                decision_reason = flow_result.get("decision_reason") or decision_reason
                decision_flags = [*decision_flags, *(flow_result.get("decision_flags") or [])]
                followup_question = flow_result.get("followup_question") or followup_question
                if flow_result.get("interview_stage"):
                    interview_stage = flow_result["interview_stage"]
                if flow_result.get("need_followup"):
                    decision_flags = [*decision_flags, "insufficient_evidence"]

        turn, deduplicated = self._session_repository.create_turn_event(
            session_id=session_id,
            event_id=payload.event_id,
            speaker=payload.speaker,
            transcript=effective_transcript,
            audio_uri=payload.audio_uri,
            confidence=effective_confidence,
            latency_ms=latency_breakdown.get("e2e_ms", payload.latency_ms),
            policy_flags=payload.policy_flags + decision_flags,
            payload={
                **payload.payload,
                "latency_breakdown": latency_breakdown,
                "degradation_mode": degradation_mode,
                "followup_question": followup_question,
                "interview_stage": interview_stage,
            },
            transcript_ttl_days=180,
            audio_ttl_days=30,
        )
        DEFAULT_INTERVIEW_EVENT_BUS.publish(
            session_id=session_id,
            event_type="session.event",
            payload={
                "event_id": payload.event_id,
                "turn_id": turn.id if turn else None,
                "speaker": payload.speaker,
                "transcript": effective_transcript,
                "accepted": not deduplicated,
                "deduplicated": deduplicated,
                "followup_question": followup_question,
                "followup_audio_uris": followup_audio_uris,
                "action": action,
                "decision_reason": decision_reason,
                "latency_breakdown": latency_breakdown,
            },
        )
        if payload.speaker == "candidate":
            transcript_preview = (effective_transcript or "").strip()
            if transcript_preview:
                logger.info(
                    "candidate_turn session=%s seq=%s accepted=%s deduplicated=%s text=%s",
                    session_id,
                    payload.seq,
                    not deduplicated,
                    deduplicated,
                    transcript_preview[:180],
                )
                # print(f"DEBUG [ASR] Session: {session_id}, Transcript: {transcript_preview}")
                # if followup_question:
                #     print(f"DEBUG [LLM] Session: {session_id}, Action: {action}, Followup: {followup_question}")
                # else:
                #     print(f"DEBUG [LLM] Session: {session_id}, No followup generated. Action: {action}, Reason: {decision_reason}")
                
                # if followup_audio_uris:
                #     print(f"DEBUG [TTS] Session: {session_id}, Audio URIs: {len(followup_audio_uris)} packets")
        return {
            "session_id": session_id,
            "event_id": payload.event_id,
            "accepted": not deduplicated,
            "deduplicated": deduplicated,
            "turn_id": turn.id if turn else None,
            "action": action,
            "decision_reason": decision_reason,
            "policy_flags": decision_flags,
            "interview_stage": interview_stage,
            "followup_question": followup_question,
            "followup_audio_uris": followup_audio_uris,
            "runtime_mode": runtime_mode,
            "model_route": model_route,
            "degradation_mode": degradation_mode,
            "latency_breakdown": latency_breakdown,
        }
        

    def generate_question_set(self, session_id: str, payload: AIInterviewQuestionGenerateRequest) -> dict:
        """基于候选人简历与岗位要求生成问题集并持久化。"""
        session_entity = self._session_repository.get(session_id)
        if not payload.force_regenerate:
            existing = self._get_existing_question_set(session_id=session_id)
            if existing is not None:
                return existing
        candidate = self._candidate_repository.get(session_entity.candidate_id)
        job = self._job_repository.get(session_entity.job_id)
        resume_text = candidate.resume_text or ""
        job_requirements = job.requirements or ""
        skills = (candidate.raw_profile or {}).get("skills", [])

        rule_questions = self._build_questions(
            resume_text=resume_text,
            job_requirements=job_requirements,
            skills=skills,
            question_count=payload.question_count,
            language=session_entity.language,
        )
        questions = list(rule_questions)
        if self._is_interview_llm_enabled():
            llm_questions = self._build_questions_with_llm(
                session_id=session_id,
                resume_text=resume_text,
                job_requirements=job_requirements,
                skills=skills,
                question_count=payload.question_count,
                language=session_entity.language,
            )
            if llm_questions:
                questions = self._merge_question_candidates(
                    rule_questions=rule_questions,
                    llm_questions=llm_questions,
                    question_count=payload.question_count,
                    resume_text=resume_text,
                    job_requirements=job_requirements,
                    skills=skills,
                    language=session_entity.language,
                )
        latest_version = self._session_repository.get_latest_question_set_version(session_id)
        version = latest_version + 1
        self._session_repository.create_question_set(
            session_id=session_id,
            version=version,
            source=payload.source,
            questions=questions,
        )
        question_pack = {
            "session_id": session_id,
            "version": version,
            "source": payload.source,
            "language": session_entity.language,
            "question_count": len(questions),
            "questions": questions,
        }
        self._runtime_store.save_question_pack(
            session_id=session_id,
            version=version,
            question_pack=question_pack,
            ttl_seconds=int(self._settings.ai_interview_question_pack_ttl_seconds),
        )
        return {
            "session_id": session_id,
            "version": version,
            "question_count": len(questions),
            "source": payload.source,
            "questions": questions,
        }

    def prebuild_question_pack(self, payload: AIInterviewQuestionPackPrebuildRequest) -> dict:
        """预生成题包并缓存到运行时存储。"""
        candidate = self._candidate_repository.get(payload.candidate_id)
        job = self._job_repository.get(payload.job_id)
        resume_text = candidate.resume_text or ""
        job_requirements = job.requirements or ""
        skills = (candidate.raw_profile or {}).get("skills", [])
        rule_questions = self._build_questions(
            resume_text=resume_text,
            job_requirements=job_requirements,
            skills=skills,
            question_count=payload.question_count,
            language=payload.language,
        )
        questions = list(rule_questions)
        if self._is_interview_llm_enabled():
            llm_questions = self._build_questions_with_llm(
                session_id=f"prebuild:{payload.candidate_id}:{payload.job_id}",
                resume_text=resume_text,
                job_requirements=job_requirements,
                skills=skills,
                question_count=payload.question_count,
                language=payload.language,
            )
            if llm_questions:
                questions = self._merge_question_candidates(
                    rule_questions=rule_questions,
                    llm_questions=llm_questions,
                    question_count=payload.question_count,
                    resume_text=resume_text,
                    job_requirements=job_requirements,
                    skills=skills,
                    language=payload.language,
                )
        resume_hash = self._compute_prebuild_resume_hash(
            resume_text=resume_text,
            job_requirements=job_requirements,
            skills=skills,
        )
        cache_key = self._build_prebuild_cache_key(
            job_id=payload.job_id,
            candidate_id=payload.candidate_id,
            language=payload.language,
            resume_hash=resume_hash,
        )
        question_pack = {
            "candidate_id": payload.candidate_id,
            "job_id": payload.job_id,
            "language": payload.language,
            "source": payload.source,
            "question_count": len(questions),
            "questions": questions,
            "resume_hash": resume_hash,
        }
        ttl_seconds = int(self._settings.ai_interview_prebuild_pack_ttl_seconds)
        self._runtime_store.save_prebuilt_pack(
            key=cache_key,
            question_pack=question_pack,
            ttl_seconds=ttl_seconds,
        )
        return {
            "cache_key": cache_key,
            "question_count": len(questions),
            "expires_in_seconds": ttl_seconds,
            "source": payload.source,
        }

    def get_report(
        self,
        session_id: str,
        *,
        run_id: str | None = None,
        force_recompute: bool = False,
    ) -> AIInterviewReportResponse:
        """查询会话报告，支持 run_id 复算与回放。"""
        runtime_mode = self._resolve_runtime_mode()
        turns = self._session_repository.list_turns(session_id)
        resolved_run_id = run_id or self._build_run_id(session_id=session_id, runtime_mode=runtime_mode, turns=turns)
        report_entity = self._session_repository.get_report_by_run_id(session_id, resolved_run_id)
        if report_entity is None and not force_recompute:
            report_entity = self._session_repository.get_latest_report(session_id)
        if report_entity is None or force_recompute:
            report_entity = self._build_and_persist_report(session_id, runtime_mode=runtime_mode, turns=turns, run_id=resolved_run_id)
        return AIInterviewReportResponse(
            session_id=session_id,
            report_version=report_entity.report_version,
            summary=report_entity.summary,
            dimension_scores=report_entity.dimension_scores_json,
            risk_tags=report_entity.risk_tags_json,
            recommendation=report_entity.recommendation,
            runtime_mode=runtime_mode,
            run_id=str((report_entity.payload or {}).get("run_id", resolved_run_id)),
        )

    def get_replay(self, session_id: str, *, limit: int = 50, offset: int = 0) -> AIInterviewReplayResponse:
        """返回会话回放数据，支持按 turn 粒度定位。"""
        self._session_repository.get(session_id)
        turns = self._session_repository.list_turns(session_id)
        paged = turns[max(0, offset) : max(0, offset) + max(1, min(limit, 200))]
        items = [
            {
                "turn_id": item.id,
                "turn_no": item.turn_no,
                "speaker": item.speaker,
                "transcript": item.transcript,
                "audio_uri": item.audio_uri,
                "confidence": item.confidence,
                "latency_ms": item.latency_ms,
                "policy_flags": list(item.policy_flags or []),
                "occurred_at": item.created_at,
            }
            for item in paged
        ]
        return AIInterviewReplayResponse(session_id=session_id, total_turns=len(turns), items=items)

    def get_metrics(self, *, window_minutes: int, min_samples: int = 5) -> AIInterviewMetricsResponse:
        """聚合 handoff/blocked/latency 指标并给出告警原因。"""
        sessions = self._session_repository.list_sessions(window_minutes=window_minutes)
        total = len(sessions)
        handoff_count = sum(1 for item in sessions if item.status == "failed" and (item.payload or {}).get("handoff_reason"))
        blocked_count = sum(1 for item in sessions if item.status == "failed" and (item.payload or {}).get("blocked_reason"))
        handoff_rate = round(handoff_count / total, 4) if total > 0 else 0.0
        blocked_rate = round(blocked_count / total, 4) if total > 0 else 0.0

        turns = self._session_repository.list_candidate_turns(window_minutes=window_minutes)
        e2e_latencies = [int(item.latency_ms) for item in turns if item.latency_ms is not None]
        asr_latencies = []
        llm_latencies = []
        tts_latencies = []
        llm_first_token_latencies = []
        tts_first_packet_latencies = []
        prefetch_hits = 0
        prefetch_total = 0
        followup_questions: list[str] = []
        candidate_turn_count_by_session: dict[str, int] = {}
        for item in turns:
            candidate_turn_count_by_session[item.session_id] = candidate_turn_count_by_session.get(item.session_id, 0) + 1
            breakdown = (item.payload or {}).get("latency_breakdown", {})
            if isinstance(breakdown, dict):
                if isinstance(breakdown.get("asr_ms"), int):
                    asr_latencies.append(int(breakdown["asr_ms"]))
                if isinstance(breakdown.get("llm_ms"), int):
                    llm_latencies.append(int(breakdown["llm_ms"]))
                if isinstance(breakdown.get("tts_ms"), int):
                    tts_latencies.append(int(breakdown["tts_ms"]))
                if isinstance(breakdown.get("llm_first_token_ms"), int):
                    llm_first_token_latencies.append(int(breakdown["llm_first_token_ms"]))
                if isinstance(breakdown.get("tts_first_packet_ms"), int):
                    tts_first_packet_latencies.append(int(breakdown["tts_first_packet_ms"]))
                if isinstance(breakdown.get("llm_prefetch_hit"), int):
                    prefetch_total += 1
                    prefetch_hits += 1 if int(breakdown["llm_prefetch_hit"]) > 0 else 0
            followup = str((item.payload or {}).get("followup_question") or "").strip()
            if followup:
                followup_questions.append(followup)

        def _percentile(values: list[int], p: float) -> float:
            if not values:
                return 0.0
            ordered = sorted(values)
            rank = max(1, min(len(ordered), int(len(ordered) * p + 0.9999)))
            return float(ordered[rank - 1])

        asr_p50 = _percentile(asr_latencies, 0.50)
        asr_p95 = _percentile(asr_latencies, 0.95)
        asr_p99 = _percentile(asr_latencies, 0.99)
        llm_p50 = _percentile(llm_latencies, 0.50)
        llm_p95 = _percentile(llm_latencies, 0.95)
        llm_p99 = _percentile(llm_latencies, 0.99)
        tts_p50 = _percentile(tts_latencies, 0.50)
        tts_p95 = _percentile(tts_latencies, 0.95)
        tts_p99 = _percentile(tts_latencies, 0.99)
        llm_first_token_p95 = _percentile(llm_first_token_latencies, 0.95)
        tts_first_packet_p95 = _percentile(tts_first_packet_latencies, 0.95)
        e2e_p50 = _percentile(e2e_latencies, 0.50)
        e2e_p95 = _percentile(e2e_latencies, 0.95)
        e2e_p99 = _percentile(e2e_latencies, 0.99)
        followup_repeat_rate = 0.0
        if followup_questions:
            followup_repeat_rate = round((len(followup_questions) - len(set(followup_questions))) / len(followup_questions), 4)
        prefetch_hit_rate = round(prefetch_hits / prefetch_total, 4) if prefetch_total > 0 else 0.0
        completion_rate_values: list[float] = []
        for item in sessions:
            payload = dict(item.payload or {})
            raw_completion_rate = payload.get("question_completion_rate")
            if isinstance(raw_completion_rate, (int, float)):
                completion_rate_values.append(float(raw_completion_rate))
                continue

            flow = payload.get("question_flow")
            if isinstance(flow, dict):
                completed_questions = int(flow.get("completed_questions") or 0)
                total_questions = int(flow.get("total_questions") or 0)
                if total_questions > 0:
                    completion_rate_values.append(min(1.0, completed_questions / total_questions))
                    continue

            total_questions = int(payload.get("question_count") or 0)
            if total_questions > 0:
                turn_count = int(candidate_turn_count_by_session.get(item.id, 0))
                completion_rate_values.append(min(1.0, turn_count / total_questions))

        question_completion_rate = (
            round(sum(completion_rate_values) / len(completion_rate_values), 4)
            if completion_rate_values
            else 0.0
        )
        video_policy_applied_count = sum(1 for item in sessions if bool((item.payload or {}).get("rtc_video_policy_applied")))
        video_recording_enabled_count = sum(1 for item in sessions if bool((item.payload or {}).get("rtc_video_record_enabled")))
        video_policy_applied_rate = round(video_policy_applied_count / total, 4) if total > 0 else 0.0
        video_recording_enabled_rate = round(video_recording_enabled_count / total, 4) if total > 0 else 0.0

        alert_reasons: list[str] = []
        if total >= min_samples and handoff_rate >= 0.30:
            alert_reasons.append("handoff_rate_high")
        if total >= min_samples and blocked_rate >= 0.10:
            alert_reasons.append("blocked_rate_high")
        if e2e_latencies and e2e_p95 > 1800:
            alert_reasons.append("latency_p95_high")
        if asr_latencies and asr_p95 > 700:
            alert_reasons.append("asr_latency_p95_high")
        if llm_latencies and llm_p95 > 800:
            alert_reasons.append("llm_latency_p95_high")
        if tts_latencies and tts_p95 > 700:
            alert_reasons.append("tts_latency_p95_high")
        return AIInterviewMetricsResponse(
            window_minutes=window_minutes,
            total=total,
            handoff_count=handoff_count,
            blocked_count=blocked_count,
            handoff_rate=handoff_rate,
            blocked_rate=blocked_rate,
            asr_p50_ms=round(asr_p50, 2),
            asr_p95_ms=round(asr_p95, 2),
            asr_p99_ms=round(asr_p99, 2),
            llm_p50_ms=round(llm_p50, 2),
            llm_p95_ms=round(llm_p95, 2),
            llm_p99_ms=round(llm_p99, 2),
            tts_p50_ms=round(tts_p50, 2),
            tts_p95_ms=round(tts_p95, 2),
            tts_p99_ms=round(tts_p99, 2),
            e2e_p50_ms=round(e2e_p50, 2),
            e2e_p95_ms=round(e2e_p95, 2),
            e2e_p99_ms=round(e2e_p99, 2),
            latency_p95_ms=round(e2e_p95, 2),
            llm_first_token_p95_ms=round(llm_first_token_p95, 2),
            tts_first_packet_p95_ms=round(tts_first_packet_p95, 2),
            followup_repeat_rate=followup_repeat_rate,
            prefetch_hit_rate=prefetch_hit_rate,
            question_completion_rate=question_completion_rate,
            video_policy_applied_count=video_policy_applied_count,
            video_policy_applied_rate=video_policy_applied_rate,
            video_recording_enabled_count=video_recording_enabled_count,
            video_recording_enabled_rate=video_recording_enabled_rate,
            alerting=bool(alert_reasons),
            alert_reasons=alert_reasons,
        )

    def rtc_join(self, session_id: str, payload: AIInterviewRTCJoinRequest) -> AIInterviewRTCJoinResponse:
        """RTC-001：候选人入会，支持后续重连。"""
        entity = self._session_repository.get(session_id)
        if payload.candidate_id != entity.candidate_id:
            raise InvalidStateError("candidate_id 与会话不匹配")
        join_info = self._rtc_gateway.join_room(
            session_id=session_id,
            room_id=entity.rtc_room_id,
            client_id=payload.client_id,
            candidate_id=payload.candidate_id,
            join_token=entity.join_token,
        )
        merged = dict(entity.payload or {})
        merged["rtc_client_id"] = payload.client_id
        merged["rtc_joined"] = True
        merged["rtc_vendor"] = join_info.vendor
        self._session_repository.update_status(session_id, status=entity.status, payload_patch=merged)
        self._event_repository.create(
            event_type="ai_interview.rtc.join",
            entity_type="ai_interview_session",
            entity_id=session_id,
            status="success",
            operator="candidate",
            session_id=session_id,
            job_id=entity.job_id,
            payload={"client_id": payload.client_id, "transport": join_info.transport, "vendor": join_info.vendor},
        )
        return AIInterviewRTCJoinResponse(
            session_id=session_id,
            room_id=join_info.room_id,
            join_token=join_info.join_token,
            reconnectable=True,
            transport=join_info.transport,
        )

    def rtc_reconnect(self, session_id: str, payload: AIInterviewRTCReconnectRequest) -> AIInterviewRTCReconnectResponse:
        """RTC-001：断线重连。"""
        entity = self._session_repository.get(session_id)
        merged = dict(entity.payload or {})
        reconnect_count = int(merged.get("rtc_reconnect_count", 0)) + 1
        reconnect_info = self._rtc_gateway.reconnect_room(
            session_id=session_id,
            room_id=entity.rtc_room_id,
            reconnect_count=reconnect_count,
            client_id=payload.client_id,
            reason=payload.reason,
        )
        self._session_repository.update_status(
            session_id,
            status=entity.status,
            payload_patch={"rtc_reconnect_count": reconnect_count, "rtc_last_reason": payload.reason, "rtc_client_id": payload.client_id},
        )
        self._event_repository.create(
            event_type="ai_interview.rtc.reconnect",
            entity_type="ai_interview_session",
            entity_id=session_id,
            status="success",
            operator="candidate",
            session_id=session_id,
            job_id=entity.job_id,
            payload={"client_id": payload.client_id, "reason": payload.reason, "reconnect_count": reconnect_count},
        )
        return AIInterviewRTCReconnectResponse(
            session_id=session_id,
            room_id=reconnect_info.room_id,
            reconnected=reconnect_info.reconnected,
            reconnect_count=reconnect_info.reconnect_count,
        )

    def rtc_subscribe_audio(self, session_id: str, payload: AIInterviewRTCAudioSubscribeRequest) -> AIInterviewRTCAudioSubscribeResponse:
        """RTC-001D：订阅候选人音轨，支持开关降级。"""
        entity = self._session_repository.get(session_id)
        if payload.candidate_id != entity.candidate_id:
            raise InvalidStateError("candidate_id 与会话不匹配")

        feature_enabled = bool(self._settings.ai_interview_rtc_audio_subscribe_enabled)
        participant_identity = (payload.participant_identity or f"{payload.candidate_id}:{payload.client_id}").strip()
        subscriber_identity = (payload.subscriber_identity or self._settings.ai_interview_rtc_audio_subscriber_identity or "ai-bot").strip()
        configured_track_sids = self._parse_track_sids_from_settings()
        track_sids = list(payload.track_sids or configured_track_sids)
        auto_subscribe = (
            payload.auto_subscribe
            if payload.auto_subscribe is not None
            else bool(self._settings.ai_interview_rtc_audio_subscribe_auto)
        )

        if not feature_enabled:
            self._event_repository.create(
                event_type="ai_interview.rtc.audio_subscribe",
                entity_type="ai_interview_session",
                entity_id=session_id,
                status="skipped",
                operator="system",
                session_id=session_id,
                job_id=entity.job_id,
                payload={"reason": "feature_disabled", "participant_identity": participant_identity, "subscriber_identity": subscriber_identity},
            )
            return AIInterviewRTCAudioSubscribeResponse(
                session_id=session_id,
                room_id=entity.rtc_room_id,
                participant_identity=participant_identity,
                subscriber_identity=subscriber_identity,
                subscribed=False,
                mode="disabled",
                track_sids=[],
                feature_enabled=False,
            )

        subscribe_info = self._rtc_gateway.subscribe_audio_tracks(
            session_id=session_id,
            room_id=entity.rtc_room_id,
            participant_identity=participant_identity,
            subscriber_identity=subscriber_identity,
            track_sids=track_sids,
            auto_subscribe=auto_subscribe,
        )
        self._session_repository.update_status(
            session_id,
            status=entity.status,
            payload_patch={
                "rtc_audio_subscribe_enabled": True,
                "rtc_audio_participant_identity": subscribe_info.participant_identity,
                "rtc_audio_subscriber_identity": subscribe_info.subscriber_identity,
                "rtc_audio_track_sids": subscribe_info.track_sids,
                "rtc_audio_subscribed": subscribe_info.subscribed,
                "rtc_audio_subscribe_mode": subscribe_info.mode,
            },
        )
        self._event_repository.create(
            event_type="ai_interview.rtc.audio_subscribe",
            entity_type="ai_interview_session",
            entity_id=session_id,
            status="success",
            operator="system",
            session_id=session_id,
            job_id=entity.job_id,
            payload={
                "participant_identity": subscribe_info.participant_identity,
                "subscriber_identity": subscribe_info.subscriber_identity,
                "track_sids": subscribe_info.track_sids,
                "mode": subscribe_info.mode,
                "auto_subscribe": auto_subscribe,
            },
        )
        return AIInterviewRTCAudioSubscribeResponse(
            session_id=session_id,
            room_id=subscribe_info.room_id,
            participant_identity=subscribe_info.participant_identity,
            subscriber_identity=subscribe_info.subscriber_identity,
            subscribed=subscribe_info.subscribed,
            mode=subscribe_info.mode,
            track_sids=subscribe_info.track_sids,
            feature_enabled=True,
        )

    def rtc_apply_video_policy(self, session_id: str, payload: AIInterviewRTCVideoPolicyRequest) -> AIInterviewRTCVideoPolicyResponse:
        """RTC-004：候选人视频上行策略与 AI 订阅/录制策略应用。"""
        entity = self._session_repository.get(session_id)
        if payload.candidate_id != entity.candidate_id:
            raise InvalidStateError("candidate_id 与会话不匹配")

        feature_enabled = bool(self._settings.ai_interview_rtc_video_policy_enabled)
        participant_identity = (payload.participant_identity or f"{payload.candidate_id}:{payload.client_id}").strip()
        subscriber_identity = (payload.subscriber_identity or self._settings.ai_interview_rtc_video_subscriber_identity or "ai-bot").strip()
        configured_track_sids = self._parse_video_track_sids_from_settings()
        track_sids = list(payload.track_sids or configured_track_sids)
        auto_subscribe = (
            payload.auto_subscribe
            if payload.auto_subscribe is not None
            else bool(self._settings.ai_interview_rtc_video_subscribe_auto)
        )
        record_enabled = (
            payload.record_enabled
            if payload.record_enabled is not None
            else bool(self._settings.ai_interview_rtc_video_record_enabled)
        )

        if not feature_enabled:
            self._event_repository.create(
                event_type="ai_interview.rtc.video_policy",
                entity_type="ai_interview_session",
                entity_id=session_id,
                status="skipped",
                operator="system",
                session_id=session_id,
                job_id=entity.job_id,
                payload={"reason": "feature_disabled", "participant_identity": participant_identity, "subscriber_identity": subscriber_identity},
            )
            return AIInterviewRTCVideoPolicyResponse(
                session_id=session_id,
                room_id=entity.rtc_room_id,
                participant_identity=participant_identity,
                subscriber_identity=subscriber_identity,
                applied=False,
                subscribed=False,
                recording_enabled=record_enabled,
                mode="disabled",
                track_sids=[],
                feature_enabled=False,
            )

        policy_info = self._rtc_gateway.apply_video_policy(
            session_id=session_id,
            room_id=entity.rtc_room_id,
            participant_identity=participant_identity,
            subscriber_identity=subscriber_identity,
            track_sids=track_sids,
            auto_subscribe=auto_subscribe,
            record_enabled=record_enabled,
        )
        self._session_repository.update_status(
            session_id,
            status=entity.status,
            payload_patch={
                "rtc_video_policy_applied": policy_info.applied,
                "rtc_video_participant_identity": policy_info.participant_identity,
                "rtc_video_subscriber_identity": policy_info.subscriber_identity,
                "rtc_video_track_sids": policy_info.track_sids,
                "rtc_video_subscribed": policy_info.subscribed,
                "rtc_video_record_enabled": policy_info.recording_enabled,
                "rtc_video_policy_mode": policy_info.mode,
            },
        )
        self._event_repository.create(
            event_type="ai_interview.rtc.video_policy",
            entity_type="ai_interview_session",
            entity_id=session_id,
            status="success",
            operator="system",
            session_id=session_id,
            job_id=entity.job_id,
            payload={
                "participant_identity": policy_info.participant_identity,
                "subscriber_identity": policy_info.subscriber_identity,
                "track_sids": policy_info.track_sids,
                "subscribed": policy_info.subscribed,
                "recording_enabled": policy_info.recording_enabled,
                "mode": policy_info.mode,
                "auto_subscribe": auto_subscribe,
            },
        )
        return AIInterviewRTCVideoPolicyResponse(
            session_id=session_id,
            room_id=policy_info.room_id,
            participant_identity=policy_info.participant_identity,
            subscriber_identity=policy_info.subscriber_identity,
            applied=policy_info.applied,
            subscribed=policy_info.subscribed,
            recording_enabled=policy_info.recording_enabled,
            mode=policy_info.mode,
            track_sids=policy_info.track_sids,
            feature_enabled=True,
        )

    def rtc_handle_livekit_webhook(
        self,
        *,
        payload: dict,
        claims: dict | None = None,
        remote_ip: str | None = None,
    ) -> dict:
        """RTC-001D: write back livekit webhook events into session state/audit timeline."""
        event_type = self._extract_livekit_event_type(payload)
        room_id = self._extract_livekit_room_id(payload)
        event_id = self._extract_livekit_event_id(payload)
        participant_identity = self._extract_livekit_participant_identity(payload)
        track_sid = self._extract_livekit_track_sid(payload)
        track_kind = self._extract_livekit_track_kind(payload)

        if not room_id:
            return {
                "accepted": False,
                "deduplicated": False,
                "vendor": "livekit",
                "event_type": event_type or None,
                "event_id": event_id,
                "room_id": None,
                "session_id": None,
                "reason": "missing_room_id",
            }

        session_entity = self._session_repository.get_by_room_id(room_id)
        if session_entity is None:
            self._event_repository.create(
                event_type="ai_interview.rtc.webhook",
                entity_type="ai_interview_session",
                entity_id=(room_id[:36] if room_id else "unknown"),
                status="skipped",
                operator="system",
                payload={
                    "vendor": "livekit",
                    "event_type": event_type,
                    "event_id": event_id,
                    "room_id": room_id,
                    "reason": "session_not_found",
                    "participant_identity": participant_identity,
                    "track_sid": track_sid,
                    "track_kind": track_kind,
                    "claims": claims or {},
                    "remote_ip": remote_ip,
                },
            )
            return {
                "accepted": False,
                "deduplicated": False,
                "vendor": "livekit",
                "event_type": event_type or None,
                "event_id": event_id,
                "room_id": room_id,
                "session_id": None,
                "reason": "session_not_found",
            }

        current_payload = dict(session_entity.payload or {})
        seen_event_ids = list(current_payload.get("rtc_webhook_seen_event_ids", []))
        if event_id in seen_event_ids:
            return {
                "accepted": True,
                "deduplicated": True,
                "vendor": "livekit",
                "event_type": event_type or None,
                "event_id": event_id,
                "room_id": room_id,
                "session_id": session_entity.id,
                "reason": None,
            }

        payload_patch: dict[str, object] = {
            "rtc_last_webhook_event_type": event_type,
            "rtc_last_webhook_event_id": event_id,
            "rtc_last_webhook_event_at": int(time.time()),
        }

        participants = {str(item).strip() for item in current_payload.get("rtc_participants", []) if str(item).strip()}
        if participant_identity and event_type in {"participant_joined", "participant_connected"}:
            participants.add(participant_identity)
            payload_patch["rtc_joined"] = True
        if participant_identity and event_type in {"participant_left", "participant_disconnected"}:
            participants.discard(participant_identity)
        if participants:
            payload_patch["rtc_participants"] = sorted(participants)
            payload_patch["rtc_participant_count"] = len(participants)
        elif event_type in {"participant_left", "participant_disconnected"}:
            payload_patch["rtc_participants"] = []
            payload_patch["rtc_participant_count"] = 0

        if event_type == "room_finished":
            payload_patch["rtc_room_closed"] = True
            payload_patch["rtc_room_closed_at"] = int(time.time())

        if track_sid:
            if track_kind == "audio":
                audio_track_sids = {
                    str(item).strip()
                    for item in current_payload.get("rtc_audio_track_sids", [])
                    if str(item).strip()
                }
                if event_type == "track_published":
                    audio_track_sids.add(track_sid)
                if event_type == "track_unpublished":
                    audio_track_sids.discard(track_sid)
                payload_patch["rtc_audio_track_sids"] = sorted(audio_track_sids)
            if track_kind == "video":
                video_track_sids = {
                    str(item).strip()
                    for item in current_payload.get("rtc_video_track_sids", [])
                    if str(item).strip()
                }
                if event_type == "track_published":
                    video_track_sids.add(track_sid)
                if event_type == "track_unpublished":
                    video_track_sids.discard(track_sid)
                payload_patch["rtc_video_track_sids"] = sorted(video_track_sids)

        auto_subscribe_applied = False
        if (
            event_type == "track_published"
            and track_kind == "audio"
            and track_sid
            and participant_identity
            and bool(self._settings.ai_interview_rtc_audio_subscribe_enabled)
        ):
            subscriber_identity = str(self._settings.ai_interview_rtc_audio_subscriber_identity or "ai-bot").strip()
            subscribe_info = self._rtc_gateway.subscribe_audio_tracks(
                session_id=session_entity.id,
                room_id=session_entity.rtc_room_id,
                participant_identity=participant_identity,
                subscriber_identity=subscriber_identity,
                track_sids=[track_sid],
                auto_subscribe=True,
            )
            payload_patch.update(
                {
                    "rtc_audio_subscribe_enabled": True,
                    "rtc_audio_participant_identity": subscribe_info.participant_identity,
                    "rtc_audio_subscriber_identity": subscribe_info.subscriber_identity,
                    "rtc_audio_subscribed": subscribe_info.subscribed,
                    "rtc_audio_subscribe_mode": subscribe_info.mode,
                }
            )
            auto_subscribe_applied = True

        seen_event_ids.append(event_id)
        payload_patch["rtc_webhook_seen_event_ids"] = seen_event_ids[-512:]
        self._session_repository.update_status(
            session_entity.id,
            status=session_entity.status,
            payload_patch=payload_patch,
        )

        self._event_repository.create(
            event_type="ai_interview.rtc.webhook",
            entity_type="ai_interview_session",
            entity_id=session_entity.id,
            status="success",
            operator="system",
            session_id=session_entity.id,
            job_id=session_entity.job_id,
            payload={
                "vendor": "livekit",
                "event_type": event_type,
                "event_id": event_id,
                "room_id": room_id,
                "participant_identity": participant_identity,
                "track_sid": track_sid,
                "track_kind": track_kind,
                "auto_subscribe_applied": auto_subscribe_applied,
                "claims": claims or {},
                "remote_ip": remote_ip,
            },
        )
        DEFAULT_INTERVIEW_EVENT_BUS.publish(
            session_id=session_entity.id,
            event_type="rtc.webhook",
            payload={
                "vendor": "livekit",
                "event_type": event_type,
                "event_id": event_id,
                "room_id": room_id,
                "participant_identity": participant_identity,
                "track_sid": track_sid,
                "track_kind": track_kind,
                "auto_subscribe_applied": auto_subscribe_applied,
            },
        )
        return {
            "accepted": True,
            "deduplicated": False,
            "vendor": "livekit",
            "event_type": event_type or None,
            "event_id": event_id,
            "room_id": room_id,
            "session_id": session_entity.id,
            "reason": None,
        }

    def rtc_ingest_audio(self, payload: AIInterviewRTCASRIngestRequest) -> dict:
        """RTC-002B/003B: ingest room audio frame then optionally trigger followup + TTS publish."""
        session_entity = self._session_repository.get_by_room_id(payload.room_id)
        if session_entity is None:
            raise InvalidStateError(f"room_id '{payload.room_id}' 未关联任何 AI 面试会话")

        asr_req = AIInterviewASRStreamRequest(
            seq=payload.seq,
            text_hint=payload.text_hint,
            audio_base64=payload.audio_base64,
            confidence=payload.confidence,
            latency_ms=payload.latency_ms,
            chunk_id=payload.frame_id,
            chunk_index=payload.chunk_index,
            chunk_total=payload.chunk_total,
            is_final=payload.is_final,
            input_format=payload.input_format,
            target_latency_ms=payload.target_latency_ms,
            source="rtc_room",
            participant_identity=payload.participant_identity,
            track_sid=payload.track_sid,
        )
        asr_resp = self.asr_stream(session_entity.id, asr_req)

        event_result: dict | None = None
        tts_result = None
        if (
            payload.auto_followup
            and payload.is_final
            and not asr_resp.deduplicated
            and (asr_resp.transcript or "").strip()
        ):
            event_req = AIInterviewSessionEventRequest(
                event_id=f"rtc-room-{payload.seq}-{payload.chunk_index}-{uuid.uuid4().hex[:8]}",
                seq=payload.seq,
                speaker="candidate",
                transcript=asr_resp.transcript,
                confidence=asr_resp.confidence,
                latency_ms=asr_resp.latency_ms,
                policy_flags=["rtc_room_ingest"],
                payload={
                    "source": "rtc_room_ingest",
                    "participant_identity": payload.participant_identity,
                    "track_sid": payload.track_sid,
                },
            )
            event_result = self.append_event(session_entity.id, event_req)
            followup_question = str((event_result or {}).get("followup_question") or "").strip()
            if payload.auto_tts_publish and followup_question:
                tts_req = AIInterviewTTSStreamRequest(
                    text=followup_question,
                    voice=payload.tts_voice,
                    chunk_size=payload.tts_chunk_size,
                    publish_to_rtc=True,
                    target_latency_ms=payload.tts_target_latency_ms,
                )
                tts_result = self.tts_stream(session_entity.id, tts_req)

        self._event_repository.create(
            event_type="ai_interview.rtc.asr_ingest",
            entity_type="ai_interview_session",
            entity_id=session_entity.id,
            status="success",
            operator="system",
            session_id=session_entity.id,
            job_id=session_entity.job_id,
            payload={
                "room_id": payload.room_id,
                "frame_id": payload.frame_id,
                "seq": payload.seq,
                "chunk_index": payload.chunk_index,
                "chunk_total": payload.chunk_total,
                "is_final": payload.is_final,
                "participant_identity": payload.participant_identity,
                "track_sid": payload.track_sid,
                "auto_followup": payload.auto_followup,
                "auto_tts_publish": payload.auto_tts_publish,
                "asr_event_id": asr_resp.event_id,
                "asr_turn_id": asr_resp.turn_id,
                "asr_deduplicated": asr_resp.deduplicated,
            },
        )
        return {
            "session_id": session_entity.id,
            "room_id": payload.room_id,
            "asr": asr_resp,
            "event": event_result,
            "tts": tts_result,
        }

    def asr_stream(self, session_id: str, payload: AIInterviewASRStreamRequest) -> AIInterviewASRStreamResponse:
        """RTC-002：ASR 流式适配，返回转写结果并落库。"""
        entity = self._session_repository.get(session_id)
        audio_bytes = getattr(payload, "audio_bytes", None)
        if self._settings.asr_force_streaming and not (payload.audio_base64 or audio_bytes) and not payload.is_final:
            raise InvalidStateError("ASR force_streaming 已开启，音频数据不可为空")
        if payload.chunk_index > payload.chunk_total:
            raise InvalidStateError("chunk_index 不能大于 chunk_total")
        ingest_start = time.perf_counter()
        asr_result = self._asr_provider.transcribe_stream(
            session_id=session_id,
            seq=payload.seq,
            text_hint=payload.text_hint,
            audio_base64=payload.audio_base64,
            audio_bytes=getattr(payload, "audio_bytes", None),
            confidence=payload.confidence,
            latency_ms=payload.latency_ms,
            chunk_index=payload.chunk_index,
            chunk_total=payload.chunk_total,
            is_final=payload.is_final,
            voice_format=payload.input_format,
        )
        total_latency_ms = int((time.perf_counter() - ingest_start) * 1000)
        provider_latency_ms = int(asr_result.latency_ms)
        adapter_latency_ms = max(0, total_latency_ms - provider_latency_ms)
        transcript = asr_result.transcript
        logger.info(
            "ASR stream result: session_id=%s, seq=%d, transcript=%s, provider=%s, total_ms=%d",
            session_id, payload.seq, transcript, asr_result.provider, total_latency_ms
        )
        event_id = payload.chunk_id or f"asr-{payload.seq}-{payload.chunk_index}"
        latency_breakdown = {
            "ingest_ms": adapter_latency_ms,
            "asr_ms": provider_latency_ms,
            "e2e_ms": total_latency_ms,
        }
        turn, deduplicated = self._session_repository.create_turn_event(
            session_id=session_id,
            event_id=event_id,
            speaker="candidate" if payload.is_final else "candidate_partial",
            transcript=transcript,
            audio_uri=None,
            confidence=asr_result.confidence,
            latency_ms=asr_result.latency_ms,
            policy_flags=["asr_stream", "asr_final" if payload.is_final else "asr_partial"],
            payload={
                "adapter": asr_result.provider,
                "seq": payload.seq,
                "chunk_id": payload.chunk_id,
                "chunk_index": payload.chunk_index,
                "chunk_total": payload.chunk_total,
                "is_final": payload.is_final,
                "input_format": payload.input_format,
                "source": payload.source,
                "participant_identity": payload.participant_identity,
                "track_sid": payload.track_sid,
                "audio_bytes": len(getattr(payload, "audio_bytes", None) or payload.audio_base64 or ""),
                "latency_breakdown": latency_breakdown,
            },
            transcript_ttl_days=180,
            audio_ttl_days=30,
        )
        self._event_repository.create(
            event_type="ai_interview.rtc.asr",
            entity_type="ai_interview_session",
            entity_id=session_id,
            status="success",
            operator="system",
            session_id=session_id,
            job_id=entity.job_id,
            payload={
                "event_id": event_id,
                "seq": payload.seq,
                "chunk_index": payload.chunk_index,
                "chunk_total": payload.chunk_total,
                "is_final": payload.is_final,
                "source": payload.source,
                "participant_identity": payload.participant_identity,
                "track_sid": payload.track_sid,
                "latency_ms": asr_result.latency_ms,
                "provider": asr_result.provider,
                "latency_breakdown": latency_breakdown,
                "deduplicated": deduplicated,
            },
        )
        if not asr_result.is_active_pushed:
            DEFAULT_INTERVIEW_EVENT_BUS.publish(
                session_id=session_id,
                event_type="asr.turn",
                payload={
                    "event_id": event_id,
                    "turn_id": turn.id if turn else None,
                    "speaker": "candidate" if payload.is_final else "candidate_partial",
                    "transcript": transcript,
                    "latency_ms": asr_result.latency_ms,
                    "chunk_index": payload.chunk_index,
                    "chunk_total": payload.chunk_total,
                    "is_final": payload.is_final,
                    "source": payload.source,
                    "participant_identity": payload.participant_identity,
                    "track_sid": payload.track_sid,
                },
            )
        realtime_target_met = asr_result.latency_ms <= payload.target_latency_ms
        return AIInterviewASRStreamResponse(
            session_id=session_id,
            seq=payload.seq,
            transcript=transcript,
            provider=asr_result.provider,
            asr_meta=dict(asr_result.metadata or {}),
            confidence=asr_result.confidence,
            latency_ms=asr_result.latency_ms,
            p95_target_met=realtime_target_met,
            event_id=event_id,
            turn_id=turn.id if turn else None,
            deduplicated=deduplicated,
            chunk_index=payload.chunk_index,
            chunk_total=payload.chunk_total,
            is_final=payload.is_final,
            is_partial=not payload.is_final,
            target_latency_ms=payload.target_latency_ms,
            realtime_target_met=realtime_target_met,
            latency_breakdown=latency_breakdown,
        )

    def tts_stream(self, session_id: str, payload: AIInterviewTTSStreamRequest) -> AIInterviewTTSStreamResponse:
        """RTC-003：TTS 流式播报，返回分片与音频地址。"""
        entity = self._session_repository.get(session_id)
        text = payload.text.strip()
        tts_start = time.perf_counter()
        if self._settings.tts_force_streaming:
            stream_chunks: list[str] = []
            stream_audio_uris: list[str] = []
            packet_index = 0
            for packet in self._tts_provider.synthesize_stream_iter(
                session_id=session_id,
                text=text,
                voice=payload.voice,
                chunk_size=payload.chunk_size,
            ):
                packet_index += 1
                packet_text = str(packet.get("text") or "")
                packet_audio_uri = str(packet.get("audio_uri") or "")
                if packet_text:
                    stream_chunks.append(packet_text)
                if packet_audio_uri:
                    stream_audio_uris.append(packet_audio_uri)
                DEFAULT_INTERVIEW_EVENT_BUS.publish(
                    session_id=session_id,
                    event_type="tts.packet",
                    payload={
                        "voice": payload.voice,
                        "packet_index": packet_index,
                        "is_final_packet": bool(packet.get("is_final_packet", False)),
                        "audio_uri": packet_audio_uri,
                        "text": packet_text,
                    },
                )
            class _TTSResult:
                def __init__(self, chunks: list[str], audio_uris: list[str], provider: str):
                    self.chunks = chunks
                    self.audio_uris = audio_uris
                    self.provider = provider
            tts_result = _TTSResult(stream_chunks, stream_audio_uris, self._tts_provider.provider_name)
        else:
            tts_result = self._tts_provider.synthesize_stream(
                session_id=session_id,
                text=text,
                voice=payload.voice,
                chunk_size=payload.chunk_size,
            )
        tts_latency_ms = int((time.perf_counter() - tts_start) * 1000)

        publish_feature_enabled = bool(self._settings.ai_interview_rtc_tts_publish_enabled)
        publish_requested = payload.publish_to_rtc if payload.publish_to_rtc is not None else publish_feature_enabled
        publish_latency_ms = 0
        published = False
        publish_mode: str | None = "disabled"
        track_sid: str | None = None
        bot_identity = (payload.bot_identity or self._settings.ai_interview_rtc_tts_bot_identity or "ai-bot").strip()
        if publish_requested:
            publish_start = time.perf_counter()
            publish_info = self._rtc_gateway.publish_bot_audio(
                session_id=session_id,
                room_id=entity.rtc_room_id,
                bot_identity=bot_identity,
                track_name=payload.track_name,
                audio_uris=list(tts_result.audio_uris),
                chunks=list(tts_result.chunks),
            )
            publish_latency_ms = int((time.perf_counter() - publish_start) * 1000)
            published = publish_info.published
            publish_mode = publish_info.mode
            track_sid = publish_info.track_sid

        latency_breakdown = {
            "tts_ms": tts_latency_ms,
            "publish_ms": publish_latency_ms,
            "e2e_ms": tts_latency_ms + publish_latency_ms,
        }
        realtime_target_met = latency_breakdown["e2e_ms"] <= payload.target_latency_ms

        self._session_repository.create_turn_event(
            session_id=session_id,
            event_id=f"tts-{uuid.uuid4().hex[:12]}",
            speaker="ai",
            transcript=text,
            audio_uri=tts_result.audio_uris[0] if tts_result.audio_uris else None,
            confidence=None,
            latency_ms=latency_breakdown["e2e_ms"],
            policy_flags=["tts_stream", "tts_published" if published else "tts_not_published"],
            payload={
                "provider": tts_result.provider,
                "voice": payload.voice,
                "chunk_size": payload.chunk_size,
                "chunk_count": len(tts_result.chunks),
                "audio_uri_count": len(tts_result.audio_uris),
                "publish_requested": publish_requested,
                "published": published,
                "publish_mode": publish_mode,
                "track_sid": track_sid,
                "bot_identity": bot_identity,
                "target_latency_ms": payload.target_latency_ms,
                "realtime_target_met": realtime_target_met,
                "latency_breakdown": latency_breakdown,
            },
            transcript_ttl_days=180,
            audio_ttl_days=30,
        )
        self._event_repository.create(
            event_type="ai_interview.rtc.tts",
            entity_type="ai_interview_session",
            entity_id=session_id,
            status="success",
            operator="system",
            session_id=session_id,
            job_id=entity.job_id,
            payload={
                "voice": payload.voice,
                "chunk_count": len(tts_result.chunks),
                "provider": tts_result.provider,
                "published": published,
                "publish_mode": publish_mode,
                "track_sid": track_sid,
                "bot_identity": bot_identity,
                "target_latency_ms": payload.target_latency_ms,
                "realtime_target_met": realtime_target_met,
                "latency_breakdown": latency_breakdown,
            },
        )
        DEFAULT_INTERVIEW_EVENT_BUS.publish(
            session_id=session_id,
            event_type="tts.ready",
            payload={
                "text": text,
                "voice": payload.voice,
                "audio_uris": list(tts_result.audio_uris),
                "published": published,
                "latency_breakdown": latency_breakdown,
            },
        )
        return AIInterviewTTSStreamResponse(
            session_id=session_id,
            voice=payload.voice,
            chunks=tts_result.chunks,
            audio_uris=tts_result.audio_uris,
            published=published,
            bot_identity=bot_identity,
            track_sid=track_sid,
            publish_mode=publish_mode,
            target_latency_ms=payload.target_latency_ms,
            realtime_target_met=realtime_target_met,
            p95_target_met=realtime_target_met,
            latency_breakdown=latency_breakdown,
        )

    def tts_stream_iter(
        self,
        *,
        session_id: str,
        text: str,
        voice: str = "default",
        chunk_size: int = 24,
    ):
        """流式生成 TTS 包，用于 duplex 首包优先推送。"""
        self._session_repository.get(session_id)
        for packet in self._tts_provider.synthesize_stream_iter(
            session_id=session_id,
            text=text,
            voice=voice,
            chunk_size=chunk_size,
        ):
            yield packet

    def process_duplex_end_of_turn(
        self,
        *,
        session_id: str,
        seq: int,
        frame_id: str | None = None,
        payload: dict | None = None,
    ) -> dict:
        """Process explicit end_of_turn message to force ASR finalization."""
        session_entity = self._session_repository.get(session_id)
        if not session_entity:
            return {"status": "ignored", "reason": "session_not_found"}
        logger.info(f"[Duplex] Explicit end_of_turn received: session={session_id} seq={seq} frame_id={frame_id}")
        self._safe_flush_asr(session_id, seq=seq)
        return {"status": "accepted", "session_id": session_id, "seq": seq}

    def _safe_flush_asr(self, session_id: str, seq: int = 1) -> None:
        """Helper to ensure ASR buffer is flushed and final response triggered."""
        try:
            # We don't have a direct 'flush' in all providers, 
            # but usually submitting an empty final chunk or closing the stream works.
            # In our current Aliyun provider, it responds to 'is_final=True'.
            asr_req = AIInterviewASRStreamRequest(
                seq=max(1, seq), 
                text_hint="",
                audio_base64=None,
                is_final=True,
                source="eot_flush"
            )
            asr_resp = self.asr_stream(session_id, asr_req)
            
            # CRITICAL: Trigger the interview logic if we got a final transcript
            is_final_resp = (asr_resp.asr_meta or {}).get("is_final") or False
            if is_final_resp and (asr_resp.transcript or "").strip():
                event_req = AIInterviewSessionEventRequest(
                    event_id=f"eot-flush-{uuid.uuid4().hex[:8]}",
                    seq=max(1, seq),
                    speaker="candidate",
                    transcript=asr_resp.transcript,
                    confidence=asr_resp.confidence,
                    payload={"source": "eot_flush"},
                )
                # print(f"DEBUG [_safe_flush_asr] Triggering append_event for session={session_id} seq={event_req.seq}")
                self.append_event(session_id, event_req)
        except Exception as e:
            logger.warning(f"Error in _safe_flush_asr for session={session_id}: {e}")

    def process_duplex_audio_chunk(
        self,
        *,
        session_id: str,
        seq: int,
        chunk_index: int,
        chunk_total: int,
        is_final: bool,
        payload: dict,
        audio_bytes: bytes | None = None,
    ) -> dict:
        """全双工实时音频分片处理：ASR -> 事件回写(可选) -> 追问/音频输出。"""
        # Use passed arguments which are already extracted/validated in the route
        frame_id = str(payload.get("frame_id") or "")
        if frame_id:
            with self._duplex_prefetch_lock:
                # Use a simple set for deduplication, capped at 1000 items
                if not hasattr(self, "_duplex_seen_frames"):
                    self._duplex_seen_frames = {} # session_id -> set
                
                seen = self._duplex_seen_frames.get(session_id)
                if seen is None:
                    seen = set()
                    self._duplex_seen_frames[session_id] = seen
                
                if frame_id in seen:
                    print(f"DEBUG [ASR Dedup] Dropping repeated frame: {frame_id}")
                    return {
                        "session_id": session_id,
                        "seq": seq,
                        "chunk_index": chunk_index,
                        "frame_id": frame_id,
                        "deduplicated": True,
                    }
                
                seen.add(frame_id)
                if len(seen) > 1000: # Simple LRU-ish cleanup
                    # Clear some space
                    self._duplex_seen_frames[session_id] = set(list(seen)[-500:])

        if is_final:
            asr_req = AIInterviewASRStreamRequest(
                seq=seq,
                text_hint=str(payload.get("text_hint") or ""),
                audio_base64=payload.get("audio_base64"),
                confidence=float(payload.get("confidence") or 0.9),
                latency_ms=int(payload.get("latency_ms") or 320),
                chunk_id=(str(payload.get("chunk_id")).strip() if payload.get("chunk_id") else None),
                chunk_index=chunk_index,
                chunk_total=chunk_total,
                is_final=is_final,
                input_format=str(payload.get("input_format") or "wav"),
                target_latency_ms=int(payload.get("target_latency_ms") or 700),
            )
            # If AIInterviewASRStreamRequest supports audio_bytes, we should set it too.
            # For now, let's at least ensure transcribe_stream below gets it.
            if hasattr(asr_req, "audio_bytes"):
                setattr(asr_req, "audio_bytes", audio_bytes)

            print(f"DEBUG [ASR In] Session: {session_id}, Audio Length: {len(audio_bytes or payload.get('audio_base64') or '')}")
            asr_resp = self.asr_stream(session_id, asr_req)
            # Flush ASR state after a final turn to avoid carry-over to next turn
            self._asr_provider.flush(session_id=session_id)
            logger.info(
                "Duplex final processing: session_id=%s, seq=%d, transcript=%s",
                session_id, seq, asr_resp.transcript
            )
        else:
            asr_start = time.perf_counter()
            partial = self._asr_provider.transcribe_stream(
                session_id=session_id,
                seq=seq,
                text_hint=str(payload.get("text_hint") or ""),
                audio_base64=payload.get("audio_base64"),
                audio_bytes=audio_bytes,
                confidence=float(payload.get("confidence") or 0.9),
                latency_ms=int(payload.get("latency_ms") or 120),
                chunk_index=chunk_index,
                chunk_total=chunk_total,
                is_final=False,
            )
            asr_resp = AIInterviewASRStreamResponse(
                session_id=session_id,
                seq=seq,
                transcript=partial.transcript,
                provider=partial.provider,
                asr_meta=dict(partial.metadata or {}),
                confidence=partial.confidence,
                latency_ms=partial.latency_ms,
                p95_target_met=True,
                event_id=None,
                turn_id=None,
                deduplicated=False,
                chunk_index=chunk_index,
                chunk_total=chunk_total,
                is_final=False,
                is_partial=True,
                target_latency_ms=int(payload.get("target_latency_ms") or 700),
                realtime_target_met=True,
                latency_breakdown={
                    "asr_ms": partial.latency_ms,
                    "e2e_ms": max(1, int((time.perf_counter() - asr_start) * 1000)),
                },
            )
            if (asr_resp.transcript or "").strip() and not partial.is_active_pushed:
                DEFAULT_INTERVIEW_EVENT_BUS.publish(
                    session_id=session_id,
                    event_type="asr.turn",
                    payload={
                        "event_id": f"asr-turn-{session_id}-{seq}-{chunk_index}",
                        "turn_id": None,
                        "speaker": "candidate_partial",
                        "transcript": asr_resp.transcript,
                        "latency_ms": asr_resp.latency_ms,
                        "chunk_index": chunk_index,
                        "chunk_total": chunk_total,
                        "is_final": False,
                    },
                )
                self._maybe_prefetch_partial_followup(
                    session_id=session_id,
                    seq=seq,
                    transcript=asr_resp.transcript,
                    confidence=asr_resp.confidence,
                    is_final=False,
                )
        event_result: dict | None = None
        if is_final and (asr_resp.transcript or "").strip():
            prefetched = self._consume_prefetched_followup(
                session_id=session_id,
                seq=seq,
                final_transcript=asr_resp.transcript,
            )
            event_payload = {"source": "duplex_ws", "duplex_mode": True}
            if prefetched:
                event_payload.update(
                    {
                        "prefetched_followup_question": prefetched["followup_question"],
                        "prefetched_llm_ms": int(prefetched.get("llm_prefetch_ms") or 0),
                        "prefetched_from_partial": True,
                    }
                )
            event_req = AIInterviewSessionEventRequest(
                event_id=f"duplex-turn-{session_id}-{seq}",
                seq=seq,
                speaker="candidate",
                transcript=asr_resp.transcript,
                confidence=asr_resp.confidence,
                latency_ms=asr_resp.latency_ms,
                policy_flags=[],
                payload=event_payload,
            )
            event_result = self.append_event(session_id, event_req)

        return {
            "session_id": session_id,
            "seq": seq,
            "chunk_index": chunk_index,
            "chunk_total": chunk_total,
            "is_final": is_final,
            "asr": asr_resp.model_dump(),
            "event": event_result,
        }

    def _maybe_prefetch_partial_followup(
        self,
        *,
        session_id: str,
        seq: int,
        transcript: str,
        confidence: float | None,
        is_final: bool = False,
    ) -> None:
        try:
            if not self._settings.ai_interview_duplex_partial_trigger_enabled:
                return
            if not bool(self._settings.ai_interview_llm_enabled):
                return
            normalized = " ".join((transcript or "").strip().split())
            min_chars = max(4, int(self._settings.ai_interview_duplex_partial_min_chars))
            if len(normalized) < min_chars:
                return
            now_ms = int(time.time() * 1000)
            cache_key = f"{session_id}:{seq}"
            dedup_ttl_ms = max(200, int(self._settings.ai_interview_duplex_partial_dedup_ttl_ms))
            text_hash = hashlib.sha1(normalized.encode("utf-8", errors="ignore")).hexdigest()[:16]
            inflight_key = f"{cache_key}:{text_hash}"

            # Single In-flight Slot: Cancel existing speculative task for this session
            with self._duplex_prefetch_lock:
                old_event = self._duplex_prefetch_abort_events.get(session_id)
                if old_event:
                    old_event.set()
                abort_event = threading.Event()
                self._duplex_prefetch_abort_events[session_id] = abort_event
                # The original logic for inflight_key check and add was here.
                # It's now moved to after the tentative/prefetch decision.
                # For now, we add it here to ensure it's tracked for cleanup.
                self._duplex_prefetch_inflight.add(inflight_key)

            # --- Tentative Execution Trigger (Wait for punctuation or length) ---
            # Lowered threshold and added fallback for long sentences without punctuation
            has_punctuation = any(p in normalized for p in ("。", "？", "！", ".", "?", "!"))
            if not is_final and (
                (len(normalized) >= 4 and has_punctuation) or 
                (len(normalized) >= 20) # Fallback for unpunctuated streams
            ):
                logger.info(f"Triggering TENTATIVE execution for session={session_id} seq={seq} transcript='{normalized}'")
                stage = "core"
                language = "zh-CN"
                try:
                    session_entity = self._session_repository.get(session_id)
                    stage = str((session_entity.payload or {}).get("interview_stage") or stage)
                    language = session_entity.language
                except Exception: pass
                
                threading.Thread(
                    target=self._run_tentative_orchestration,
                    kwargs={
                        "session_id": session_id,
                        "seq": seq,
                        "transcript": normalized,
                        "confidence": confidence,
                        "stage": stage,
                        "language": language,
                        "inflight_key": inflight_key,
                        "abort_event": abort_event,
                    },
                    daemon=True
                ).start()
                return

            # --- Background Prefetch Worker ---
            stage = "core"
            language = "zh-CN"
            try:
                session_entity = self._session_repository.get(session_id)
                language = session_entity.language
                stage = str((session_entity.payload or {}).get("interview_stage") or stage)
            except Exception: pass

            worker = threading.Thread(
                target=self._run_partial_prefetch_worker,
                kwargs={
                    "session_id": session_id,
                    "seq": seq,
                    "normalized": normalized,
                    "confidence": confidence,
                    "stage": stage,
                    "language": language,
                    "cache_key": cache_key,
                    "text_hash": text_hash,
                    "now_ms": now_ms,
                    "inflight_key": inflight_key,
                    "abort_event": abort_event,
                },
                daemon=True,
            )
            worker.start()
        except Exception as e:
            logger.error(f"Error in _maybe_prefetch_partial_followup: {e}")
            if "inflight_key" in locals():
                with self._duplex_prefetch_lock:
                    self._duplex_prefetch_inflight.discard(inflight_key)

    def _run_partial_prefetch_worker(
        self,
        *,
        session_id: str,
        seq: int,
        normalized: str,
        confidence: float | None,
        stage: str,
        language: str,
        cache_key: str,
        text_hash: str,
        now_ms: int,
        inflight_key: str,
        abort_event: threading.Event,
    ) -> None:
        from ..db.session import SessionLocal
        with SessionLocal() as session:
            worker_service = get_ai_interview_service(session)
            try:
                llm_start = time.perf_counter()
                followup_raw = worker_service._build_followup_question_with_llm(
                    session_id=session_id,
                    transcript=normalized,
                    confidence=confidence,
                    interview_stage=stage,
                    language=language,
                    write_observability=False,
                    emit_delta=False,
                    prefetch_mode=True,
                    abort_event=abort_event,
                )
                if abort_event and abort_event.is_set():
                    return

                # Robust check for generators/iterators to avoid JSON serialization errors
                if followup_raw is not None and not isinstance(followup_raw, str) and hasattr(followup_raw, "__iter__"):
                    followup_list = []
                    for chunk in followup_raw:
                        if abort_event and abort_event.is_set():
                            return
                        if isinstance(chunk, str):
                            print(chunk, end="", flush=True) # Stream print to console
                        followup_list.append(chunk)
                    print("\n") # End line
                    followup = "".join(followup_list)
                else:
                    followup = followup_raw

                llm_prefetch_ms = max(1, int((time.perf_counter() - llm_start) * 1000))
                if not followup:
                    return
                entry = {
                    "followup_question": followup,
                    "partial_transcript": normalized,
                    "text_hash": text_hash,
                    "created_at_ms": now_ms,
                    "llm_prefetch_ms": llm_prefetch_ms,
                }
                with self._duplex_prefetch_lock:
                    self._duplex_prefetch_cache[cache_key] = entry
                DEFAULT_INTERVIEW_EVENT_BUS.publish(
                    session_id=session_id,
                    event_type="llm.prefetch.ready",
                    payload={
                        "seq": seq,
                        "partial_transcript": normalized[-120:],
                        "llm_prefetch_ms": llm_prefetch_ms,
                    },
                )
            except Exception as e:
                logger.error(f"Prefetch worker error: {e}")
            finally:
                with self._duplex_prefetch_lock:
                    self._duplex_prefetch_inflight.discard(inflight_key)

    def _run_tentative_orchestration(
        self,
        *,
        session_id: str,
        seq: int,
        transcript: str,
        confidence: float | None,
        stage: str,
        language: str,
        inflight_key: str,
        abort_event: threading.Event,
    ) -> None:
        """运行后台实时编排（不写数据库）。"""
        from ..db.session import SessionLocal
        with SessionLocal() as session:
            worker_service = get_ai_interview_service(session)
            try:
                # This worker only handles TTS playback. 
                def _on_audio_packet(packet: dict) -> None:
                    if abort_event and abort_event.is_set():
                        return
                    DEFAULT_INTERVIEW_EVENT_BUS.publish(
                        session_id=session_id,
                        event_type="tts.packet",
                        payload={
                            "voice": "default",
                            "packet_index": packet.get("index"),
                            "is_final_packet": bool(packet.get("is_final_packet")),
                            "audio_uri": packet.get("audio_uri"),
                            "audio_bytes": packet.get("audio_bytes"),
                            "text": packet.get("text"),
                        },
                    )

                # Check for prefetched results first
                cache_key = f"{session_id}:{seq}"
                with self._duplex_prefetch_lock:
                    cached = self._duplex_prefetch_cache.get(cache_key)
                
                prefetched_followup = None
                if cached and cached.get("text_hash") == inflight_key.split(":")[-1]:
                     prefetched_followup = cached.get("followup_question")

                def llm_stream_wrapper(t, c, s, l):
                    return worker_service._build_followup_question_with_llm(
                        session_id=session_id,
                        transcript=t,
                        confidence=c,
                        interview_stage=s,
                        language=l,
                        write_observability=False,
                        abort_event=abort_event,
                        print_stream=True,
                    )
                llm_stream_wrapper.is_streaming = True

                worker_service._orchestrator.process_candidate_turn(
                    session_id=session_id,
                    seq=seq,
                    transcript_hint=transcript,
                    audio_base64=None,
                    confidence=confidence,
                    language=language,
                    runtime_mode="llm_full",
                    llm_enabled=prefetched_followup is None,
                    decide_action=lambda t, c: ("auto_continue", "tentative", []), 
                    build_rule_followup=lambda *args: None,
                    build_llm_followup=llm_stream_wrapper,
                    interview_stage=stage,
                    followup_question=prefetched_followup,
                    on_audio_packet=_on_audio_packet,
                )
            except Exception as e:
                logger.error(f"Tentative orchestration error: {e}")
            finally:
                with self._duplex_prefetch_lock:
                    self._duplex_prefetch_inflight.discard(inflight_key)

    def _consume_prefetched_followup(self, *, session_id: str, seq: int, final_transcript: str) -> dict | None:
        cache_key = f"{session_id}:{seq}"
        with self._duplex_prefetch_lock:
            cached = self._duplex_prefetch_cache.pop(cache_key, None)
        if not cached:
            return None
        partial_transcript = str(cached.get("partial_transcript") or "").strip()
        final_normalized = " ".join((final_transcript or "").strip().split())
        if not partial_transcript or not final_normalized:
            return None
        # Keep reuse rule lightweight for realtime path: reuse if either transcript overlaps by prefix.
        overlap_len = min(len(partial_transcript), len(final_normalized), 10)
        if overlap_len <= 0:
            return None
        if final_normalized[:overlap_len] != partial_transcript[:overlap_len]:
            return None
        return cached

    def _to_session_dict(self, entity) -> dict:
        """将会话实体转换为统一响应结构。"""
        join_url = f"/ai-interview/session/{entity.id}?token={entity.join_token}"
        return {
            "id": entity.id,
            "candidate_id": entity.candidate_id,
            "job_id": entity.job_id,
            "status": entity.status,
            "channel": entity.channel,
            "language": entity.language,
            "rtc_room_id": entity.rtc_room_id,
            "join_token": entity.join_token,
            "join_url": join_url,
            "started_at": entity.started_at,
            "ended_at": entity.ended_at,
            "payload": entity.payload,
            "note": entity.note,
            "created_at": entity.created_at,
            "updated_at": entity.updated_at,
        }

    @staticmethod
    def _extract_livekit_event_type(payload: dict) -> str:
        raw = payload.get("event") or payload.get("event_type") or payload.get("type") or ""
        return str(raw).strip().lower()

    @staticmethod
    def _extract_livekit_event_id(payload: dict) -> str:
        raw = payload.get("id") or payload.get("event_id") or payload.get("request_id")
        value = str(raw or "").strip()
        return value or f"lk-{uuid.uuid4().hex[:16]}"

    @staticmethod
    def _extract_livekit_room_id(payload: dict) -> str:
        room = payload.get("room")
        if isinstance(room, dict):
            name = room.get("name") or room.get("room")
            if name:
                return str(name).strip()
        raw = payload.get("room_id") or payload.get("room") or payload.get("room_name")
        return str(raw or "").strip()

    @staticmethod
    def _extract_livekit_participant_identity(payload: dict) -> str:
        participant = payload.get("participant")
        if isinstance(participant, dict):
            identity = participant.get("identity") or participant.get("name")
            if identity:
                return str(identity).strip()
        raw = payload.get("participant_identity") or payload.get("identity")
        return str(raw or "").strip()

    @staticmethod
    def _extract_livekit_track_sid(payload: dict) -> str:
        track = payload.get("track")
        if isinstance(track, dict):
            sid = track.get("sid") or track.get("track_sid")
            if sid:
                return str(sid).strip()
        raw = payload.get("track_sid")
        return str(raw or "").strip()

    @staticmethod
    def _extract_livekit_track_kind(payload: dict) -> str:
        track = payload.get("track")
        raw_kind = ""
        if isinstance(track, dict):
            raw_kind = str(track.get("type") or track.get("kind") or "").strip().lower()
        if not raw_kind:
            raw_kind = str(payload.get("track_kind") or "").strip().lower()
        if raw_kind in {"audio", "kind_audio", "mic"}:
            return "audio"
        if raw_kind in {"video", "kind_video", "camera"}:
            return "video"
        return raw_kind

    def _resolve_runtime_mode(self) -> str:
        """根据运行时开关解析 AI 面试运行模式。"""
        feature_key = "ai_interview_runtime"
        flag = self._runtime_repository.get_feature_flag(feature_key)
        if flag is None:
            return "llm_assist"
        if (flag.fallback_mode or "").strip() == "rule_only":
            return "rule_only"
        if flag.enabled and flag.rollout_percent >= 100:
            return "llm_full"
        return "llm_assist"

    def _load_or_init_runtime_state(self, *, session_id: str, question_pack: dict) -> dict:
        """加载会话运行态，不存在则初始化。"""
        current = self._runtime_store.get_session_state(session_id=session_id)
        if current:
            return current
        initial = self._question_flow_engine.init_state(question_pack=question_pack)
        self._runtime_store.init_session_state(
            session_id=session_id,
            state=initial,
            ttl_seconds=int(self._settings.ai_interview_state_ttl_seconds),
        )
        return initial

    def _get_active_question_context(self, *, session_id: str) -> dict | None:
        """读取当前活动题目上下文。"""
        question_pack = self._runtime_store.get_question_pack(session_id=session_id)
        if not question_pack:
            return None
        state = self._runtime_store.get_session_state(session_id=session_id)
        if not state:
            state = self._load_or_init_runtime_state(session_id=session_id, question_pack=question_pack)
        return self._question_flow_engine.current_question(state=state, question_pack=question_pack)

    def _advance_stage_by_question_flow(self, *, session_id: str, state: dict) -> str:
        """根据题流状态推进阶段。"""
        stage = self._question_flow_engine.derive_stage(state=state)
        current = self._session_repository.get(session_id)
        self._session_repository.update_status(
            session_id,
            status=current.status,
            payload_patch={"interview_stage": stage},
        )
        self._runtime_store.patch_session_state(
            session_id=session_id,
            patch={"interview_stage": stage},
            ttl_seconds=int(self._settings.ai_interview_state_ttl_seconds),
        )
        return stage

    def _update_question_flow_after_turn(
        self,
        *,
        session_id: str,
        transcript: str,
        confidence: float | None,
        question_pack: dict,
    ) -> dict:
        """基于本轮回答更新题流状态。"""
        state = self._load_or_init_runtime_state(session_id=session_id, question_pack=question_pack)
        evaluation = self._question_flow_engine.evaluate_answer(transcript=transcript, confidence=confidence)
        updated = self._question_flow_engine.apply_turn_result(
            state=state,
            evaluation=evaluation,
            max_followup_per_question=2,
        )
        updated_stage = self._question_flow_engine.derive_stage(state=updated)
        updated["interview_stage"] = updated_stage
        questions = question_pack.get("questions", []) if isinstance(question_pack, dict) else []
        total_questions = len(questions) if isinstance(questions, list) else int(question_pack.get("question_count") or 0)
        completed_questions = max(0, int(updated.get("completed_questions", 0)))
        completion_rate = (
            round(min(1.0, completed_questions / total_questions), 4)
            if total_questions > 0
            else 0.0
        )
        self._runtime_store.patch_session_state(
            session_id=session_id,
            patch=updated,
            ttl_seconds=int(self._settings.ai_interview_state_ttl_seconds),
        )
        current = self._session_repository.get(session_id)
        self._session_repository.update_status(
            session_id,
            status=current.status,
            payload_patch={
                "interview_stage": updated_stage,
                "question_count": total_questions,
                "question_completion_rate": completion_rate,
                "question_flow": {
                    "completed_questions": completed_questions,
                    "total_questions": total_questions,
                    "active_question_index": int(updated.get("active_question_index", 0)),
                    "followup_count_current": int(updated.get("followup_count_current", 0)),
                },
            },
        )
        return {
            "need_followup": bool(evaluation.get("need_followup")),
            "reason": str(evaluation.get("reason") or ""),
            "interview_stage": updated_stage,
            "question_completion_rate": completion_rate,
        }

    def _attach_prebuilt_question_pack(self, *, session_id: str) -> dict[str, object]:
        """在会话启动阶段尝试装载预生成题包。"""
        try:
            session_entity = self._session_repository.get(session_id)
            candidate = self._candidate_repository.get(session_entity.candidate_id)
            job = self._job_repository.get(session_entity.job_id)
            resume_hash = self._compute_prebuild_resume_hash(
                resume_text=candidate.resume_text or "",
                job_requirements=job.requirements or "",
                skills=(candidate.raw_profile or {}).get("skills", []),
            )
            cache_key = self._build_prebuild_cache_key(
                job_id=session_entity.job_id,
                candidate_id=session_entity.candidate_id,
                language=session_entity.language,
                resume_hash=resume_hash,
            )
            prebuilt_pack = self._runtime_store.get_prebuilt_pack(key=cache_key)
            if not prebuilt_pack:
                return {"prebuilt_pack_hit": False}
            questions = prebuilt_pack.get("questions", [])
            if not isinstance(questions, list) or not questions:
                return {"prebuilt_pack_hit": False}
            latest_version = self._session_repository.get_latest_question_set_version(session_id)
            version = latest_version + 1
            source = str(prebuilt_pack.get("source") or "prebuilt")
            self._session_repository.create_question_set(
                session_id=session_id,
                version=version,
                source=source,
                questions=questions,
            )
            hydrated_pack = {
                "session_id": session_id,
                "version": version,
                "source": source,
                "language": session_entity.language,
                "question_count": len(questions),
                "questions": questions,
                "cache_key": cache_key,
            }
            self._runtime_store.save_question_pack(
                session_id=session_id,
                version=version,
                question_pack=hydrated_pack,
                ttl_seconds=int(self._settings.ai_interview_question_pack_ttl_seconds),
            )
            return {
                "prebuilt_pack_hit": True,
                "prebuilt_cache_key": cache_key,
                "question_pack_version": version,
                "question_pack_source": source,
            }
        except Exception:
            return {"prebuilt_pack_hit": False}

    def _build_prebuild_cache_key(self, *, job_id: str, candidate_id: str, language: str, resume_hash: str) -> str:
        """构建预生成题包 key。"""
        normalized_lang = (language or "zh-CN").strip()
        normalized_hash = (resume_hash or "").strip()[:16]
        return f"{job_id}:{candidate_id}:{normalized_lang}:{normalized_hash}"

    @staticmethod
    def _compute_prebuild_resume_hash(*, resume_text: str, job_requirements: str, skills: list[str]) -> str:
        """计算预生成题包内容哈希。"""
        material = {
            "resume_text": (resume_text or "")[:4000],
            "job_requirements": (job_requirements or "")[:1200],
            "skills": [str(item).strip() for item in skills if str(item).strip()],
        }
        encoded = json.dumps(material, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _get_existing_question_set(self, *, session_id: str) -> dict | None:
        """Return the latest generated question set when regeneration is not required."""
        cached = self._runtime_store.get_question_pack(session_id=session_id)
        if cached and isinstance(cached.get("questions"), list) and cached.get("version") is not None:
            questions = [item for item in cached.get("questions", []) if isinstance(item, dict)]
            return {
                "session_id": session_id,
                "version": int(cached.get("version")),
                "question_count": len(questions),
                "source": str(cached.get("source") or "runtime_cache"),
                "questions": questions,
            }
        latest = self._session_repository.get_latest_question_set(session_id)
        if latest is None:
            return None
        questions = [item for item in (latest.questions_json or []) if isinstance(item, dict)]
        question_pack = {
            "session_id": session_id,
            "version": int(latest.version),
            "source": latest.source,
            "question_count": len(questions),
            "questions": questions,
        }
        self._runtime_store.save_question_pack(
            session_id=session_id,
            version=int(latest.version),
            question_pack=question_pack,
            ttl_seconds=int(self._settings.ai_interview_question_pack_ttl_seconds),
        )
        return {
            "session_id": session_id,
            "version": int(latest.version),
            "question_count": len(questions),
            "source": latest.source,
            "questions": questions,
        }

    @staticmethod
    def _normalize_question_item(item: dict | object) -> dict | None:
        if not isinstance(item, dict):
            return None
        question = str(item.get("question") or "").strip()
        if not question:
            return None
        return {
            "question": question,
            "dimension": str(item.get("dimension") or "communication").strip() or "communication",
            "expected_signal": str(item.get("expected_signal") or "").strip(),
            "followup_condition": str(item.get("followup_condition") or "").strip(),
        }

    @staticmethod
    def _extract_keyword_tokens(*, skills: list[str], job_requirements: str, resume_text: str, language: str) -> set[str]:
        tokens = {str(item).strip().lower() for item in (skills or []) if str(item).strip()}
        text = f"{(job_requirements or '')[:500]} {(resume_text or '')[:500]}".lower()
        if language == "en-US":
            for token in re.findall(r"[a-z][a-z0-9_+\-.]{2,}", text):
                tokens.add(token)
        else:
            for term in ("性能", "并发", "架构", "稳定性", "排查", "数据库", "系统", "上线", "故障", "可用性", "扩展性"):
                if term in text:
                    tokens.add(term)
        return {token for token in tokens if token}

    def _score_question_item(self, *, question: dict, source: str, keyword_tokens: set[str], language: str) -> int:
        text = f"{question.get('question', '')} {question.get('expected_signal', '')} {question.get('followup_condition', '')}".lower()
        base = 58 if source == "llm" else 48
        if question.get("expected_signal"):
            base += 8
        if question.get("followup_condition"):
            base += 6
        hit_count = sum(1 for token in keyword_tokens if token and token in text)
        base += min(20, hit_count * 4)

        dimension = str(question.get("dimension") or "").strip().lower()
        if dimension in {"project_experience", "problem_solving", "ownership", "job_fit", "communication", "system_design"}:
            base += 6
        question_len = len(str(question.get("question") or ""))
        if 18 <= question_len <= 120:
            base += 4
        if language == "en-US":
            if any(term in text for term in ("latency", "throughput", "tradeoff", "incident", "scalability", "observability")):
                base += 8
        else:
            if any(term in text for term in ("性能", "并发", "架构", "排查", "指标", "容量", "稳定性", "故障", "权衡")):
                base += 8
        return base

    def _merge_question_candidates(
        self,
        *,
        rule_questions: list[dict],
        llm_questions: list[dict],
        question_count: int,
        resume_text: str,
        job_requirements: str,
        skills: list[str],
        language: str,
    ) -> list[dict]:
        """Blend rule + LLM questions, deduplicate and keep dimension diversity."""
        keyword_tokens = self._extract_keyword_tokens(
            skills=skills,
            job_requirements=job_requirements,
            resume_text=resume_text,
            language=language,
        )
        candidates: list[dict] = []
        for source, questions in (("rule", rule_questions), ("llm", llm_questions)):
            for raw in questions:
                normalized = self._normalize_question_item(raw)
                if normalized is None:
                    continue
                normalized_text = re.sub(r"\s+", " ", normalized["question"]).strip().lower()
                if not normalized_text:
                    continue
                candidates.append(
                    {
                        "source": source,
                        "normalized_text": normalized_text,
                        "score": self._score_question_item(
                            question=normalized,
                            source=source,
                            keyword_tokens=keyword_tokens,
                            language=language,
                        ),
                        "question": normalized,
                    }
                )
        if not candidates:
            return list(rule_questions)[:question_count]

        dedup: dict[str, dict] = {}
        for item in sorted(candidates, key=lambda entry: entry["score"], reverse=True):
            key = item["normalized_text"]
            if key not in dedup:
                dedup[key] = item
        ranked = list(dedup.values())
        ranked.sort(key=lambda entry: (entry["score"], 1 if entry["source"] == "llm" else 0), reverse=True)

        picked: list[dict] = []
        seen_dimensions: set[str] = set()
        for item in ranked:
            question = item["question"]
            dimension = str(question.get("dimension") or "communication").strip().lower()
            if dimension and dimension in seen_dimensions:
                continue
            picked.append(question)
            if dimension:
                seen_dimensions.add(dimension)
            if len(picked) >= question_count:
                return picked

        for item in ranked:
            question = item["question"]
            if question in picked:
                continue
            picked.append(question)
            if len(picked) >= question_count:
                break
        return picked[:question_count]

    def _resolve_prompt_template(self, *, task_key: str, default_version: str) -> PromptTemplate:
        """Resolve active runtime prompt template; fallback to bundled template library."""
        active_prompt = self._runtime_repository.get_active_prompt(task_key)
        if active_prompt is not None:
            runtime_system = str(active_prompt.system_prompt or "").strip()
            runtime_user = str(active_prompt.user_template or "").strip()
            runtime_version = str(active_prompt.version or default_version).strip() or default_version
            if runtime_system and runtime_user:
                return PromptTemplate(
                    task_key=task_key,
                    version=runtime_version,
                    system_prompt=runtime_system,
                    user_template=runtime_user,
                )
            try:
                return get_prompt_template(task_key, runtime_version)
            except KeyError:
                logger.warning("Prompt template not found for task=%s version=%s, fallback=%s", task_key, runtime_version, default_version)
        return get_prompt_template(task_key, default_version)

    def _build_followup_prompt_context(
        self,
        *,
        session_id: str,
        transcript: str,
        confidence: float | None,
        interview_stage: str,
        language: str,
    ) -> dict[str, str]:
        """构建追问 Prompt 上下文。"""
        compact_answer = " ".join((transcript or "").strip().split())[:320]
        active_question = self._get_active_question_context(session_id=session_id) or {}
        current_question = str(active_question.get("question") or "请结合当前问题补充细节。").strip()
        expected_signal = str(active_question.get("expected_signal") or "挖掘候选人陈述的项目细节、核心难点或技术决策背景").strip()
        turns = self._session_repository.list_recent_turns(session_id, limit=4)
        summaries: list[str] = []
        for item in turns:
            text = " ".join((item.transcript or "").strip().split())
            if not text:
                continue
            speaker = "候选人" if item.speaker == "candidate" else "AI"
            summaries.append(f"{speaker}:{text[:240]}")
        # Handle next question preview for v4 natural transition
        next_q_text = ""
        try:
            # Look ahead for the next question to help the AI decide whether to transition
            q_pack = self._runtime_store.get_question_pack(session_id=session_id)
            if q_pack:
                state = self._runtime_store.get_session_state(session_id=session_id)
                current_idx = state.get("current_question_index", 0)
                if current_idx + 1 < len(q_pack):
                    next_q = q_pack[current_idx + 1]
                    next_q_text = f"\n备选下一个正式问题：{next_q.get('question')}\n"
        except Exception:
            pass

        return {
            "language": language,
            "stage": interview_stage,
            "current_question": current_question,
            "expected_signal": expected_signal,
            "answer": compact_answer,
            "last_turns_summary": " | ".join(summaries) if summaries else "无历史上下文",
            "confidence": f"{confidence:.2f}" if confidence is not None else "",
            "next_question_section": next_q_text,
        }

    def _parse_track_sids_from_settings(self) -> list[str]:
        raw = (self._settings.ai_interview_rtc_audio_track_ids or "").strip()
        if not raw:
            return []
        return [item.strip() for item in raw.split(",") if item.strip()]

    def _parse_video_track_sids_from_settings(self) -> list[str]:
        raw = (self._settings.ai_interview_rtc_video_track_ids or "").strip()
        if not raw:
            return []
        return [item.strip() for item in raw.split(",") if item.strip()]

    def _decide_interview_action(self, *, session_id: str, transcript: str, confidence: float | None) -> tuple[str, str, list[str]]:
        """根据敏感和置信度策略决定继续、拦截或转人工。"""
        runtime_mode = self._resolve_runtime_mode()
        if runtime_mode == "rule_only":
            return "auto_continue", "rule_only_mode", []

        sensitive_keywords = ("身份证", "银行卡", "宗教", "种族", "违法")
        flags: list[str] = []
        for keyword in sensitive_keywords:
            if keyword in (transcript or ""):
                flags.append(f"sensitive:{keyword}")

        if flags:
            self._session_repository.create_handoff(
                session_id=session_id,
                reason="sensitive_content",
                trigger_flags=flags,
                operator="system",
                payload={"transcript": transcript[:200]},
            )
            self._session_repository.update_status(
                session_id,
                status="failed",
                payload_patch={"blocked_reason": "sensitive_content", "blocked_flags": flags},
            )
            return "blocked", "sensitive_content", flags

        min_confidence = 0.60
        max_low_streak = 2
        session_entity = self._session_repository.get(session_id)
        session_payload = dict(session_entity.payload or {})
        low_streak = int(session_payload.get("low_confidence_streak", 0))
        if confidence is not None and confidence < min_confidence:
            low_streak += 1
            flags.append("low_confidence")
            self._session_repository.update_status(
                session_id,
                status=session_entity.status,
                payload_patch={"low_confidence_streak": low_streak},
            )
            if low_streak >= max_low_streak:
                self._session_repository.create_handoff(
                    session_id=session_id,
                    reason="low_confidence_streak",
                    trigger_flags=flags,
                    operator="system",
                    payload={"confidence": confidence, "streak": low_streak},
                )
                self._session_repository.update_status(
                    session_id,
                    status="failed",
                    payload_patch={"handoff_reason": "low_confidence_streak", "low_confidence_streak": low_streak},
                )
                return "handoff", "low_confidence_streak", flags
            return "auto_continue", "low_confidence_but_within_threshold", flags

        if low_streak != 0:
            self._session_repository.update_status(
                session_id,
                status=session_entity.status,
                payload_patch={"low_confidence_streak": 0},
            )
        return "auto_continue", "confidence_passed", flags

    def _advance_stage(self, session_id: str) -> str:
        """BE-011：根据候选人回答轮次推进面试阶段，支持重入。"""
        turns = self._session_repository.list_turns(session_id)
        candidate_turn_count = len([item for item in turns if item.speaker == "candidate"])
        if candidate_turn_count <= 2:
            stage = "intro"
        elif candidate_turn_count <= 5:
            stage = "core"
        else:
            stage = "deep_dive"
        current = self._session_repository.get(session_id)
        self._session_repository.update_status(
            session_id,
            status=current.status,
            payload_patch={"interview_stage": stage},
        )
        return stage

    def _build_followup_question(
        self,
        *,
        transcript: str,
        confidence: float | None,
        interview_stage: str | None,
        language: str,
        action: str | None,
    ) -> str | None:
        """BE-012：生成可解释追问内容，异常分支降级为空。"""
        if action in {"handoff", "blocked"}:
            return None
        if confidence is not None and confidence < 0.60:
            if language == "en-US":
                return "Please answer with one concrete case, including context, actions, and measurable result."
            return "请用一个具体案例补充你的回答，包含背景、行动与结果。"
        if len((transcript or "").strip()) < 18:
            if language == "en-US":
                return f"We are in {interview_stage or 'core'} stage, please add more detail and measurable outcomes."
            return f"当前处于 {interview_stage or 'core'} 阶段，请补充更多细节和量化结果。"
        return None

    def _build_questions(
        self,
        *,
        resume_text: str,
        job_requirements: str,
        skills: list[str],
        question_count: int,
        language: str,
    ) -> list[dict]:
        """用规则方式生成结构化问题，保证输出稳定可解释。"""
        normalized_skills = [str(item).strip() for item in (skills or []) if str(item).strip()]
        if not normalized_skills:
            normalized_skills = ["项目经验", "技术栈匹配", "问题定位能力"]

        question_bank: list[dict] = []
        for skill in normalized_skills:
            if language == "en-US":
                question_bank.append(
                    {
                        "question": f"Please share one project where you applied {skill} and the measurable outcome.",
                        "dimension": "project_experience",
                        "expected_signal": "Clear ownership and measurable impact",
                        "followup_condition": "Follow up if answer lacks concrete metrics",
                    }
                )
                question_bank.append(
                    {
                        "question": f"If a production incident is related to {skill}, how would you diagnose and recover?",
                        "dimension": "problem_solving",
                        "expected_signal": "Structured diagnosis and recovery steps",
                        "followup_condition": "Follow up if steps are missing",
                    }
                )
            else:
                question_bank.append(
                    {
                        "question": f"请介绍你在 {skill} 相关项目中的实践和结果。",
                        "dimension": "project_experience",
                        "expected_signal": "可量化的项目结果与个人贡献",
                        "followup_condition": "回答不具体或缺少结果指标时追问",
                    }
                )
                question_bank.append(
                    {
                        "question": f"如果线上出现与 {skill} 相关故障，你会如何定位并恢复？",
                        "dimension": "problem_solving",
                        "expected_signal": "定位步骤清晰，兼顾止损和根因分析",
                        "followup_condition": "只给结论缺少步骤时追问",
                    }
                )

        job_hint = job_requirements[:120] if job_requirements else "岗位要求"
        if language == "en-US":
            question_bank.extend(
                [
                    {
                        "question": f"Given the role requirement '{job_hint}', what are your top three matching strengths?",
                        "dimension": "job_fit",
                        "expected_signal": "Direct mapping from experience to requirement",
                        "followup_condition": "Follow up if mapping is vague",
                    },
                    {
                        "question": "What was the most complex project you led in the last year? How did you break down milestones?",
                        "dimension": "ownership",
                        "expected_signal": "Clear leadership and milestone ownership",
                        "followup_condition": "Follow up if ownership is unclear",
                    },
                    {
                        "question": "Tell me about a conflict in collaboration and how you drove alignment.",
                        "dimension": "communication",
                        "expected_signal": "Conflict handling with clear outcomes",
                        "followup_condition": "Follow up if no concrete resolution is given",
                    },
                ]
            )
        else:
            question_bank.extend(
                [
                    {
                        "question": f"结合岗位要求“{job_hint}”，你认为自己最匹配的三点是什么？",
                        "dimension": "job_fit",
                        "expected_signal": "能将经历与岗位要求逐条映射",
                        "followup_condition": "匹配点空泛或缺证据时追问",
                    },
                    {
                        "question": "过去一年你主导过的最复杂项目是什么？你如何拆解目标与里程碑？",
                        "dimension": "ownership",
                        "expected_signal": "目标拆解清晰，体现主导能力",
                        "followup_condition": "未体现主导职责时追问",
                    },
                    {
                        "question": "请分享一次与团队协作出现分歧的经历，你如何推进达成一致？",
                        "dimension": "communication",
                        "expected_signal": "沟通策略与结果闭环明确",
                        "followup_condition": "缺少冲突处理细节时追问",
                    },
                ]
            )
        return question_bank[:question_count]

    def _build_and_persist_report(self, session_id: str, *, runtime_mode: str, turns=None, run_id: str):
        """根据会话轮次生成简版报告并持久化。"""
        session_entity = self._session_repository.get(session_id)
        turns = turns or self._session_repository.list_turns(session_id)
        candidate_turns = [item for item in turns if item.speaker == "candidate"]
        candidate_texts = [item.transcript.strip() for item in candidate_turns if (item.transcript or "").strip()]
        summary = "；".join(candidate_texts[:3]) if candidate_texts else "候选人有效回答较少，建议人工复核。"

        confidences = [item.confidence for item in candidate_turns if item.confidence is not None]
        avg_confidence = (sum(confidences) / len(confidences)) if confidences else 0.0
        communication_score = min(100.0, 55.0 + len(candidate_texts) * 8.0)
        technical_depth_score = round(max(0.0, min(100.0, avg_confidence * 100.0)), 2)
        job_fit_score = min(100.0, 60.0 + len(candidate_texts) * 5.0)
        dimension_scores = {
            "communication": round(communication_score, 2),
            "technical_depth": technical_depth_score,
            "job_fit": round(job_fit_score, 2),
        }
        total_score = round(sum(dimension_scores.values()) / len(dimension_scores), 2)

        risk_tags: list[str] = []
        if not candidate_texts:
            risk_tags.append("insufficient_response")
        if avg_confidence < 0.55:
            risk_tags.append("low_confidence_answers")
        if any("sensitive:" in flag for turn in candidate_turns for flag in (turn.policy_flags or [])):
            risk_tags.append("sensitive_content")

        recommendation = "advance" if total_score >= 75 and "sensitive_content" not in risk_tags else "manual_review"
        latest_report = self._session_repository.get_latest_report(session_id)
        report_version = (latest_report.report_version + 1) if latest_report else 1
        report_entity = self._session_repository.create_report(
            session_id=session_id,
            report_version=report_version,
            summary=summary[:2000],
            dimension_scores_json=dimension_scores,
            risk_tags_json=risk_tags,
            recommendation=recommendation,
            payload={"runtime_mode": runtime_mode, "total_score": total_score, "run_id": run_id},
        )

        # BE-007: 回写既有 candidate/interview 状态与审计事件。
        self._candidate_repository.update_score(
            session_entity.candidate_id,
            total_score=total_score,
            dimensions=dimension_scores,
            explanation=summary[:500],
        )
        self._candidate_repository.update_stage(session_entity.candidate_id, "interview_done")
        interview_status = "confirmed" if recommendation == "advance" else "rejected"
        if hasattr(self._interview_repository, "update_latest_status_by_job_candidate"):
            self._interview_repository.update_latest_status_by_job_candidate(
                job_id=session_entity.job_id,
                candidate_id=session_entity.candidate_id,
                status=interview_status,
                payload_patch={"ai_interview_report_id": report_entity.id, "ai_recommendation": recommendation},
            )
        self._event_repository.create(
            event_type="ai_interview.report.generated",
            entity_type="ai_interview_session",
            entity_id=session_id,
            status="success",
            operator="system",
            session_id=session_id,
            job_id=session_entity.job_id,
            payload={
                "candidate_id": session_entity.candidate_id,
                "job_id": session_entity.job_id,
                "report_id": report_entity.id,
                "recommendation": recommendation,
                "total_score": total_score,
                "risk_tags": risk_tags,
            },
        )
        return report_entity

    def _build_run_id(self, *, session_id: str, runtime_mode: str, turns) -> str:
        """根据输入快照生成可复算 run_id。"""
        material = {
            "session_id": session_id,
            "runtime_mode": runtime_mode,
            "turns": [
                {
                    "turn_no": item.turn_no,
                    "speaker": item.speaker,
                    "transcript": item.transcript,
                    "confidence": item.confidence,
                    "policy_flags": list(item.policy_flags or []),
                }
                for item in turns
            ],
        }
        digest = hashlib.sha256(json.dumps(material, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        return f"run_{digest[:16]}"

    def _resolve_model_route(self, session_id: str) -> str:
        """BE-016：根据策略选择成本优先或质量优先模型路由。"""
        session_entity = self._session_repository.get(session_id)
        route_policy = str((session_entity.payload or {}).get("model_route_policy", "quality_first")).strip()
        if route_policy == "cost_first":
            return "cost_optimized"
        if route_policy == "balanced":
            return "balanced"
        return "quality_max"

    def _is_interview_llm_enabled(self) -> bool:
        """判定面试链路是否启用 LLM。"""
        return self._runtime_repository.is_feature_enabled(
            feature_key="ai_interview_llm",
            default_enabled=self._settings.ai_interview_llm_enabled,
        )

    def _build_questions_with_llm(
        self,
        *,
        session_id: str,
        resume_text: str,
        job_requirements: str,
        skills: list[str],
        question_count: int,
        language: str,
    ) -> list[dict]:
        """使用 LLM 生成问题树，失败时返回空列表用于回退。"""
        template = self._resolve_prompt_template(task_key="interview_question_set", default_version="v1")
        try:
            rendered = template.render(
                language=language,
                job_requirements=job_requirements[:1200],
                resume_text=resume_text[:3000],
                skills=skills,
                question_count=question_count,
            )
        except KeyError:
            logger.warning("Invalid runtime prompt placeholders for task=interview_question_set, fallback to bundled v1")
            template = get_prompt_template("interview_question_set", "v1")
            rendered = template.render(
                language=language,
                job_requirements=job_requirements[:1200],
                resume_text=resume_text[:3000],
                skills=skills,
                question_count=question_count,
            )
        prompt = f"{template.system_prompt}\n{rendered}"
        result = self._llm_client.invoke_json(
            InvokeContext(
                task_key="interview_question_set",
                trace_id=f"ai-intv-q-{session_id}-{uuid.uuid4().hex[:8]}",
                prompt=prompt,
                entity_type="ai_interview_session",
                entity_id=session_id,
            )
        )
        payload = result.content if isinstance(result.content, dict) else {}
        questions = payload.get("questions", [])
        cleaned: list[dict] = []
        for item in questions:
            if not isinstance(item, dict):
                continue
            cleaned.append(
                {
                    "question": str(item.get("question") or "").strip(),
                    "dimension": str(item.get("dimension") or "communication").strip(),
                    "expected_signal": str(item.get("expected_signal") or "").strip(),
                    "followup_condition": str(item.get("followup_condition") or "").strip(),
                }
            )
        cleaned = [item for item in cleaned if item["question"]]
        return cleaned[:question_count]

    def _build_followup_question_with_llm(
        self,
        *,
        session_id: str,
        transcript: str,
        confidence: float | None,
        interview_stage: str,
        language: str,
        write_observability: bool = True,
        emit_delta: bool = True,
        prefetch_mode: bool = False,
        abort_event: threading.Event | None = None,
        print_stream: bool = False,
    ):
        """使用 LLM 生成实时追问，以生成器形式返回句子流。"""
        template = self._resolve_prompt_template(task_key="interview_followup", default_version="v4")
        prompt_ctx = self._build_followup_prompt_context(
            session_id=session_id,
            transcript=transcript,
            confidence=confidence,
            interview_stage=interview_stage,
            language=language,
        )
        try:
            rendered = template.render(**prompt_ctx)
        except KeyError:
            logger.warning("Invalid runtime prompt placeholders for task=interview_followup, fallback to bundled v3")
            template = get_prompt_template("interview_followup", "v3")
            rendered = template.render(**prompt_ctx)
        prompt = f"{template.system_prompt}\n{rendered}"
        llm_client = self._llm_prefetch_client if prefetch_mode else self._llm_client
        
        # Flush ASR buffer as we are now pivoting to an AI response turn
        if self._asr_provider:
            try:
                self._asr_provider.flush(session_id=session_id)
                logger.debug(f"ASR buffer flushed for session={session_id} as AI starts speaking")
            except Exception as e:
                logger.warning(f"Failed to flush ASR: {e}")

        logger.info(f"LLM Follow-up Streaming Prompt: {prompt[:200]}...")
        
        # 使用 split_sentences 包装 LLM 流
        text_stream = llm_client.stream_invoke(
            InvokeContext(
                task_key="interview_followup",
                trace_id=f"ai-intv-fu-stream-{session_id}-{uuid.uuid4().hex[:8]}",
                prompt=prompt,
                entity_type="ai_interview_session",
                entity_id=session_id,
            ),
            write_observability=write_observability,
        )

        from .orchestrator.streaming_utils import split_sentences
        for sentence in split_sentences(text_stream):
            if abort_event and abort_event.is_set():
                logger.info(f"Speculative LLM task aborted for session={session_id}")
                return
            if emit_delta:
                DEFAULT_INTERVIEW_EVENT_BUS.publish(
                    session_id=session_id,
                    event_type="llm.sentence",
                    payload={"text": sentence, "is_final": False}
                )
            if print_stream:
                print(f"Speculative LLM Sentence: {sentence}", flush=True)
            yield sentence

    # 标记该方法为流式，以便编排器识别
    _build_followup_question_with_llm.is_streaming = True


def _get_singleton_asr_provider() -> "ASRProvider":
    """返回进程级 ASR Provider 单例（双检锁）。"""
    global _ASR_PROVIDER_SINGLETON
    if _ASR_PROVIDER_SINGLETON is None:
        with _PROVIDER_SINGLETON_LOCK:
            if _ASR_PROVIDER_SINGLETON is None:
                _ASR_PROVIDER_SINGLETON = create_asr_provider(get_settings())
                logger.info("[Provider] ASR provider singleton created: %s", type(_ASR_PROVIDER_SINGLETON).__name__)
    return _ASR_PROVIDER_SINGLETON


def _get_singleton_tts_provider() -> "TTSProvider":
    """返回进程级 TTS Provider 单例（双检锁）。"""
    global _TTS_PROVIDER_SINGLETON
    if _TTS_PROVIDER_SINGLETON is None:
        with _PROVIDER_SINGLETON_LOCK:
            if _TTS_PROVIDER_SINGLETON is None:
                _TTS_PROVIDER_SINGLETON = create_tts_provider(get_settings())
                logger.info("[Provider] TTS provider singleton created: %s", type(_TTS_PROVIDER_SINGLETON).__name__)
    return _TTS_PROVIDER_SINGLETON


def get_ai_interview_service(session: Session) -> AIInterviewService:
    """返回绑定当前 DB 会话的 AI 面试服务实例。

    ASR/TTS provider 为进程级单例，不随 DB session 重建，
    避免 NLS 等有状态 provider 每次请求都重新握手。
    """
    settings = get_settings()
    runtime_repository = AIRuntimeRepository(session)
    llm_client = LLMClient(
        router=ModelRouter(runtime_repository),
        guardrail_service=GuardrailService(),
        observability_repository=AIObservabilityRepository(session),
    )
    asr_provider = _get_singleton_asr_provider()
    tts_provider = _get_singleton_tts_provider()
    return AIInterviewService(
        session_repository=AIInterviewSessionRepository(session),
        runtime_repository=runtime_repository,
        candidate_repository=CandidateRepository(session),
        job_repository=JobRepository(session),
        interview_repository=InterviewRepository(session),
        event_repository=EventRepository(session),
        rtc_gateway=create_rtc_gateway(settings),
        asr_provider=asr_provider,
        tts_provider=tts_provider,
        llm_client=llm_client,
        runtime_store=get_interview_runtime_store(),
        orchestrator=RealtimeOrchestrator(
            asr_provider=asr_provider,
            tts_provider=tts_provider,
        ),
    )
