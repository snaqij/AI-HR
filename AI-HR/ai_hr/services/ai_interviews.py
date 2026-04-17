"""AI 闈㈣瘯浼氳瘽鏈嶅姟銆?"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

# 鈹€鈹€ 杩涚▼绾?Provider 鍗曚緥锛堝弻妫€閿侊級鈹€鈹€
# AliyunNlsASRProvider 缁存姢 NLS WebSocket 闀胯繛鎺ワ紝蹇呴』鍏ㄥ眬澶嶇敤銆?
# 姣忔璋冪敤 get_ai_interview_service 鑻ラ噸鏂?create_asr_provider锛?
# 浼氫负姣忎釜闊抽 chunk 鏂板缓杩炴帴锛岀珛鍗宠Е鍙?TOO_MANY_REQUESTS銆?
_PROVIDER_SINGLETON_LOCK = threading.Lock()
_ASR_PROVIDER_SINGLETON: "ASRProvider | None" = None
_TTS_PROVIDER_SINGLETON: "TTSProvider | None" = None

# Turn-level deduplication markers for duplex flow
_DUPLEX_FINALIZE_LOCK = threading.Lock()
_DUPLEX_FINALIZED_SEQ: dict[str, set[int]] = {}
_DUPLEX_TIMELINE_LOCK = threading.Lock()
_DUPLEX_TIMELINE_MARKERS: dict[str, dict[int, dict[str, int]]] = {}
from sqlalchemy.orm import Session
from ..copy.ai_interviews import (
    DEFAULT_TTS_VOICE,
    FOLLOWUP_DEFAULT_QUESTION,
    FOLLOWUP_DEFAULT_SIGNAL,
    FOLLOWUP_SPEAKER_AI,
    FOLLOWUP_SPEAKER_CANDIDATE,
    INSUFFICIENT_EVIDENCE_FLAG,
    LLM_PREFETCH_FROM_PARTIAL_FLAG,
    LOW_CONFIDENCE_FLAG,
    RECENT_CONTEXT_EMPTY,
    REPORT_EMPTY_SUMMARY,
)
from ..core.config import get_settings
from ..core.exceptions import InvalidStateError
from ..db.session import SessionLocal
from ..domain.constants import (
    BlockReason,
    CandidateStageResult,
    HandoffReason,
    InterviewAction,
    InterviewEventType,
    InterviewOutcomeStatus,
    InterviewRecommendation,
    InterviewSessionStatus,
    InterviewStage,
    InterviewStageGroup,
    ModelRoutePolicy,
    ModelRouteResult,
    PayloadKey,
    PromptTaskKey,
    RiskTag,
    RuntimeMode,
    SENSITIVE_FLAG_PREFIX,
    SpeakerRole,
    build_sensitive_flag,
)
from ..repositories.ai_interviews import (
    AIInterviewInvitationRepository,
    AIInterviewSessionRepository,
)
from ..repositories.ai_observability import AIObservabilityRepository
from ..repositories.ai_runtime import AIRuntimeRepository
from ..repositories.candidates import CandidateRepository
from ..repositories.events import EventRepository
from ..repositories.interviews import InterviewRepository
from ..repositories.jobs import JobRepository
from ..schemas.ai_interviews import (
    AIInterviewASRStreamRequest,
    AIInterviewASRStreamResponse,
    AIInterviewInvitationResponse,
    AIInterviewMetricsResponse,
    AIInterviewQuestionGenerateRequest,
    AIInterviewQuestionGenerateResult,
    AIInterviewQuestionPackPrebuildRequest,
    AIInterviewRTCAudioSubscribeRequest,
    AIInterviewRTCAudioSubscribeResponse,
    AIInterviewRTCASRIngestRequest,
    AIInterviewRTCJoinRequest,
    AIInterviewRTCJoinResponse,
    AIInterviewRTCReconnectRequest,
    AIInterviewRTCReconnectResponse,
    AIInterviewRTCVideoPolicyRequest,
    AIInterviewRTCVideoPolicyResponse,
    AIInterviewReplayResponse,
    AIInterviewReportResponse,
    AIInterviewSessionCreateRequest,
    AIInterviewSessionEventRequest,
    AIInterviewSessionFinishRequest,
    AIInterviewSessionHandoffRequest,
    AIInterviewSessionStartRequest,
    AIInterviewTENRuntimeResponse,
    AIInterviewTTSStreamRequest,
    AIInterviewTTSStreamResponse,
)
from .interview_runtime.question_flow import InterviewQuestionFlowEngine
from .interview_runtime.question_schema import normalize_question_item, normalize_question_pack
from .interview_runtime.question_seed_builder import build_stage_seed_questions
from .interview_runtime.runtime_engine import InterviewRuntimeEngine
from .interview_runtime.store import InterviewRuntimeStore
from .interview_runtime import get_interview_runtime_store
from .llm.client import InvokeContext, LLMClient
from .llm.guardrails import GuardrailService
from .llm.prompts import PromptTemplate, get_prompt_template
from .llm.router import ModelRouter
from .orchestrator.event_bus import DEFAULT_INTERVIEW_EVENT_BUS
from .orchestrator.realtime import RealtimeOrchestrator
from .rtc.base import RTCGateway
from .rtc.factory import create_rtc_gateway
from .speech.base import ASRProvider, TTSProvider
from .speech.factory import create_asr_provider, create_tts_provider
from .ten_runtime import TENRuntimeManager

# 鈹€鈹€ 杩涚▼绾?Provider 鍗曚緥锛堝弻妫€閿侊級鈹€鈹€
# AliyunNlsASRProvider 缁存姢 NLS WebSocket 闀胯繛鎺ワ紝蹇呴鬱鍏ㄥ眬澶嶇敤銆?
# 姣忔璋冪敤 get_ai_interview_service 鑻ラ噸鏂?create_asr_provider锛?
# 浼氫负姣忎釜闊抽 chunk 鏂板缓杩炴帴锛岀珛鍗卽瑙﹀彂 TOO_MANY_REQUESTS銆?
_PROVIDER_SINGLETON_LOCK = threading.Lock()
_ASR_PROVIDER_SINGLETON: "ASRProvider | None" = None
_TTS_PROVIDER_SINGLETON: "TTSProvider | None" = None

# Turn-level deduplication markers for duplex flow
_DUPLEX_FINALIZE_LOCK = threading.Lock()
_DUPLEX_FINALIZED_SEQ: dict[str, set[int]] = {}
_DUPLEX_TIMELINE_LOCK = threading.Lock()
_DUPLEX_TIMELINE_MARKERS: dict[str, dict[int, dict[str, int]]] = {}

logger = logging.getLogger(__name__)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _record_duplex_timeline_marker(
    *,
    session_id: str,
    seq: int,
    marker_key: str,
    at_ms: int | None = None,
    overwrite: bool = False,
) -> int:
    safe_seq = max(1, int(seq or 1))
    safe_at_ms = int(at_ms or _now_ms())
    with _DUPLEX_TIMELINE_LOCK:
        session_markers = _DUPLEX_TIMELINE_MARKERS.setdefault(session_id, {})
        seq_markers = session_markers.setdefault(safe_seq, {})
        if overwrite or marker_key not in seq_markers:
            seq_markers[marker_key] = safe_at_ms
        return int(seq_markers[marker_key])


def _get_duplex_timeline_markers(*, session_id: str, seq: int) -> dict[str, int]:
    safe_seq = max(1, int(seq or 1))
    with _DUPLEX_TIMELINE_LOCK:
        return dict((_DUPLEX_TIMELINE_MARKERS.get(session_id, {}) or {}).get(safe_seq, {}) or {})


class AIInterviewService:
    """鎻愪緵 AI 闈㈣瘯浼氳瘽缂栨帓鑳藉姏銆?"""

    def __init__(
        self,
        *,
        session_repository: AIInterviewSessionRepository,
        invitation_repository: AIInterviewInvitationRepository,
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
        ten_runtime_manager: TENRuntimeManager | None = None,
    ):
        self._settings = get_settings()
        self._session_repository = session_repository
        self._invitation_repository = invitation_repository
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
        self._ten_runtime_manager = ten_runtime_manager or TENRuntimeManager(self._settings)
        self._question_flow_engine = InterviewQuestionFlowEngine()
        self._runtime_engine = InterviewRuntimeEngine(question_flow_engine=self._question_flow_engine)
        self._duplex_prefetch_lock = threading.Lock()
        self._duplex_prefetch_cache: dict[str, dict] = {}
        self._duplex_prefetch_inflight: set[str] = set()
        self._duplex_prefetch_abort_events: dict[str, threading.Event] = {}

    def create_invitation(self, candidate_id: str, job_id: str, note: str | None = None) -> AIInterviewInvitationResponse:
        """创建面试邀请链接并触发题目预生成。"""
        # 0. 验证候选人和岗位是否存在
        self._candidate_repository.get(candidate_id)
        job = self._job_repository.get(job_id)

        # 1. 生成 Token 和有效期 (3天)
        token = uuid.uuid4().hex
        expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=3)

        # 2. 创建邀请记录
        entity = self._invitation_repository.create(
            candidate_id=candidate_id,
            job_id=job_id,
            token=token,
            expires_at=expires_at,
            note=note
        )

        # 3. 立即自动触发题目生成
        try:
            # 使用空 session_id，传入 invitation_id
            self.generate_question_set(invitation_id=entity.id)
            self._invitation_repository.update_status(entity.id, "ready")
        except Exception as e:
            logger.error("Failed to auto-generate questions for invitation %s: %s", entity.id, e)
            # 保持 pending 状态，后续访问时会再次尝试生成

        return AIInterviewInvitationResponse(
            id=entity.id,
            token=entity.token,
            candidate_id=entity.candidate_id,
            job_id=entity.job_id,
            status=entity.status,
            expires_at=entity.expires_at,
            job_title=job.title or "Unknown"
        )

    def get_invitation_by_token(self, token: str) -> AIInterviewInvitationResponse:
        """获取邀请链接详情并校验。"""
        entity = self._invitation_repository.get_by_token(token)
        now = datetime.now(UTC).replace(tzinfo=None)
        
        if entity.expires_at < now:
            self._invitation_repository.update_status(entity.id, "expired")
            raise InvalidStateError(f"Invitation link with token '{token}' has expired")
            
        job = self._job_repository.get(entity.job_id)
        return AIInterviewInvitationResponse(
            id=entity.id,
            token=entity.token,
            candidate_id=entity.candidate_id,
            job_id=entity.job_id,
            status=entity.status,
            expires_at=entity.expires_at,
            job_title=job.title or "Unknown"
        )

    def activate_invitation(self, token: str, operator: str = "candidate") -> dict:
        """通过邀请链接激活面试，创建新 Session。"""
        invitation = self._invitation_repository.get_by_token(token)
        now = datetime.now(UTC).replace(tzinfo=None)
        
        # 1. 严格校验：有效期与单次使用限制
        if invitation.expires_at < now:
            self._invitation_repository.update_status(invitation.id, "expired")
            raise InvalidStateError("邀请链接已过期 (Expired)")
            
        if invitation.used_count >= invitation.max_use_count:
            raise InvalidStateError(f"邀请链接已达到最大使用次数 ({invitation.max_use_count})")

        # 2. 创建全新的 Session (哪怕之前退出过)
        session_create_req = AIInterviewSessionCreateRequest(
            candidate_id=invitation.candidate_id,
            job_id=invitation.job_id,
            channel="invitation_link",
            language="zh-CN",
            note=invitation.note,
            payload={"invitation_token": token}
        )
        session_dict = self.create_session(session_create_req)
        session_id = session_dict["id"]

        # 3. 检查是否有预生成的题目包，并关联到新 Session
        prebuilt_set = self._session_repository.get_latest_question_set(invitation_id=invitation.id)
        if prebuilt_set:
            version = self._session_repository.get_latest_question_set_version(session_id) + 1
            self._session_repository.create_question_set(
                session_id=session_id,
                invitation_id=invitation.id,
                version=version,
                source=prebuilt_set.source,
                questions=prebuilt_set.questions_json
            )
            
        # 4. 关键：标记邀请链接为已激活（增加已使用次数）
        self._invitation_repository.mark_activated(invitation.id)

        # 5. 启动 Session
        start_req = AIInterviewSessionStartRequest(operator=operator)
        return self.start_session(session_id, start_req)

    def create_session(self, payload: AIInterviewSessionCreateRequest) -> dict:
        """鍒涘缓 AI 闈㈣瘯浼氳瘽骞惰繑鍥炲叆浼氫俊鎭€?"""
        self._candidate_repository.get(payload.candidate_id)
        job = self._job_repository.get(payload.job_id)

        join_token = uuid.uuid4().hex
        rtc_room_id = f"ai-intv-{uuid.uuid4()}"
        rtc_info = self._rtc_gateway.create_room(session_id=f"{payload.candidate_id}:{payload.job_id}", preferred_room_id=rtc_room_id)

        runtime_company_payload = self._build_runtime_company_payload(
            job_id=payload.job_id,
            job_requirements=job.requirements or "",
            payload=dict(payload.payload),
        )

        entity = self._session_repository.create(
            candidate_id=payload.candidate_id,
            job_id=payload.job_id,
            channel=payload.channel,
            language=payload.language,
            rtc_room_id=rtc_info.room_id,
            join_token=rtc_info.join_token or join_token,
            note=payload.note,
            payload={
                "interview_stage": InterviewStage.OPENING,
                **self._build_rtc_payload(rtc_info),
                **runtime_company_payload,
                **dict(payload.payload),
            },
        )
        entity = self._session_repository.update_status(
            entity.id,
            status=entity.status,
            payload_patch={
                "ten_enabled": bool(self._settings.ai_interview_ten_enabled),
                "ten_launch_status": "pending_start" if self._settings.ai_interview_ten_enabled else "disabled",
            },
        )
        return self._to_session_dict(entity)

    def get_session(self, session_id: str) -> dict:
        """鑾峰彇 AI 闈㈣瘯浼氳瘽璇︽儏銆?"""
        entity = self._session_repository.get(session_id)
        return self._to_session_dict(entity)

    def start_session(self, session_id: str, payload: AIInterviewSessionStartRequest) -> dict:
        """鍚姩 AI 闈㈣瘯浼氳瘽銆?"""
        entity = self._session_repository.get(session_id)
        if entity.status != InterviewSessionStatus.CREATED:
            raise InvalidStateError(f"AI interview session '{session_id}' cannot start from status '{entity.status}'")
        # Prewarm ASR/TTS connection to reduce first-turn latency spikes.
        self.asr_warmup(session_id=session_id)
        self.tts_warmup(session_id=session_id, voice=DEFAULT_TTS_VOICE)
        
        prebuilt_patch = self._attach_prebuilt_question_pack(session_id=session_id)
        payload_patch = {"last_operator": payload.operator}
        payload_patch.update(prebuilt_patch)
        question_pack = self._ensure_runtime_question_pack_for_start(session_id=session_id)
        if question_pack:
            state = self._reset_runtime_state_for_start(session_id=session_id, question_pack=question_pack)
            payload_patch[PayloadKey.INTERVIEW_STAGE] = self._question_flow_engine.derive_stage(
                state=state,
                question_pack=question_pack,
            )
            payload_patch["question_pack"] = question_pack
            payload_patch["question_count"] = int(question_pack.get("question_count") or 0)
            payload_patch["question_pack_version"] = int(question_pack.get("version") or 0)
            payload_patch["question_pack_source"] = str(
                question_pack.get("source") or payload_patch.get("question_pack_source") or ""
            )
        else:
            logger.error(
                "ai_interview.start_session_question_pack_unavailable session_id=%s",
                session_id,
            )
        entity = self._session_repository.update_status(
            session_id,
            status=InterviewSessionStatus.IN_PROGRESS,
            payload_patch=payload_patch,
        )
        ten_patch = self._prepare_ten_runtime(entity)
        if ten_patch:
            entity = self._session_repository.update_status(
                entity.id,
                status=entity.status,
                payload_patch=ten_patch,
            )
        if question_pack:
            self._log_runtime_start_snapshot(session_id=session_id, question_pack=question_pack)
        return self._to_session_dict(entity)

    def asr_warmup(self, session_id: str) -> None:
        """棰勭儹 ASR 杩炴帴銆?"""
        try:
            self._asr_provider.warmup(session_id=session_id)
        except Exception:
            pass

    def tts_warmup(self, session_id: str, voice: str = DEFAULT_TTS_VOICE) -> None:
        """棰勭儹 TTS 璧勬簮銆?"""
        try:
            self._tts_provider.warmup(session_id=session_id, voice=voice)
        except Exception:
            pass

    def finish_session(self, session_id: str, payload: AIInterviewSessionFinishRequest) -> dict:
        """缁撴潫 AI 闈㈣瘯浼氳瘽銆?"""
        entity = self._session_repository.get(session_id)
        if entity.status != InterviewSessionStatus.IN_PROGRESS:
            raise InvalidStateError(f"AI interview session '{session_id}' cannot finish from status '{entity.status}'")
        entity = self._session_repository.update_status(
            session_id,
            status=payload.result_status,
            note=payload.note,
            payload_patch={"finish_operator": payload.operator, PayloadKey.INTERVIEW_STAGE: InterviewStage.CLOSING},
        )
        return self._to_session_dict(entity)

    def handoff_session(self, session_id: str, payload: AIInterviewSessionHandoffRequest) -> dict:
        """灏嗕細璇濊浆浜哄伐骞跺啓鍏?handoff 璁板綍銆?"""
        entity = self._session_repository.get(session_id)
        if entity.status != InterviewSessionStatus.IN_PROGRESS:
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
            status=InterviewSessionStatus.FAILED,
            payload_patch={
                "handoff_id": handoff.id,
                PayloadKey.HANDOFF_REASON: payload.reason,
                "handoff_operator": payload.operator,
            },
        )
        return {
            "session": self._to_session_dict(entity),
            "handoff_id": handoff.id,
        }

    def append_event(self, session_id: str, payload: AIInterviewSessionEventRequest) -> dict:
        """涓婃姤瀹炴椂浜嬩欢骞舵寜 event_id 鍘婚噸銆?"""
        entity = self._session_repository.get(session_id)
        if entity.status != InterviewSessionStatus.IN_PROGRESS:
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
            if payload.speaker == SpeakerRole.CANDIDATE and (payload.transcript or "").strip():
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
                PayloadKey.INTERVIEW_STAGE: None,
                PayloadKey.FOLLOWUP_QUESTION: None,
                "followup_audio_uris": [],
                PayloadKey.RUNTIME_MODE: runtime_mode,
                "model_route": model_route,
                PayloadKey.DEGRADATION_MODE: None,
                PayloadKey.LATENCY_BREAKDOWN: {},
            }

        if payload.speaker == SpeakerRole.CANDIDATE:
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
                if packet.get("audio_bytes") and not packet.get("_first_pcm_marker_recorded"):
                    packet["tts_first_pcm_at_ms"] = _record_duplex_timeline_marker(
                        session_id=session_id,
                        seq=payload.seq,
                        marker_key="tts_first_pcm_at_ms",
                    )
                    packet["_first_pcm_marker_recorded"] = True
                DEFAULT_INTERVIEW_EVENT_BUS.publish(
                    session_id=session_id,
                    event_type=InterviewEventType.TTS_PACKET,
                    payload=packet,
                )

            def llm_stream_wrapper(t, c, s, l):
                return self._build_followup_question_with_llm(
                    session_id=session_id,
                    seq=payload.seq,
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

            if prefetched_followup and action not in {InterviewAction.HANDOFF, InterviewAction.BLOCKED}:
                followup_question = prefetched_followup
                original_llm_ms = int(latency_breakdown.get("llm_ms") or 0)
                latency_breakdown["llm_ms"] = 0
                latency_breakdown["llm_prefetch_hit"] = 1
                latency_breakdown["llm_prefetch_ms"] = max(0, prefetched_llm_ms)
                latency_breakdown["e2e_ms"] = max(1, int(latency_breakdown.get("e2e_ms") or 0) - original_llm_ms)
                if prefetched_from_partial:
                    decision_flags = [*decision_flags, LLM_PREFETCH_FROM_PARTIAL_FLAG]

            latency_breakdown.update(self._build_turn_timeline_breakdown(session_id=session_id, seq=payload.seq))

            effective_confidence = payload.confidence if payload.confidence is not None else 0.9
            if question_pack and action not in {InterviewAction.HANDOFF, InterviewAction.BLOCKED}:
                flow_result = self._update_question_flow_after_turn(
                    session_id=session_id,
                    transcript=effective_transcript or "",
                    confidence=effective_confidence,
                    question_pack=question_pack,
                )
                if flow_result.get(PayloadKey.INTERVIEW_STAGE):
                    interview_stage = flow_result[PayloadKey.INTERVIEW_STAGE]
                if flow_result.get("need_followup"):
                    decision_flags = [*decision_flags, INSUFFICIENT_EVIDENCE_FLAG]
                    decision_reason = flow_result.get("reason") or decision_reason

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
                PayloadKey.LATENCY_BREAKDOWN: latency_breakdown,
                PayloadKey.DEGRADATION_MODE: degradation_mode,
                PayloadKey.FOLLOWUP_QUESTION: followup_question,
                PayloadKey.INTERVIEW_STAGE: interview_stage,
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
                PayloadKey.FOLLOWUP_QUESTION: followup_question,
                "followup_audio_uris": followup_audio_uris,
                "action": action,
                "decision_reason": decision_reason,
                PayloadKey.LATENCY_BREAKDOWN: latency_breakdown,
            },
        )

    def finalize_session_turn(self, session_id: str) -> dict:
        """Manually trigger the finalization of the current turn (force AI response)."""
        entity = self._session_repository.get(session_id)
        if entity.status != InterviewSessionStatus.IN_PROGRESS:
            raise InvalidStateError(f"AI interview session '{session_id}' is not in progress.")

        # Publish force_finalize event to the bus. 
        # The agent (orchestrator) will listen for this and trigger immediate processing.
        DEFAULT_INTERVIEW_EVENT_BUS.publish(
            session_id=session_id,
            event_type=InterviewEventType.CANDIDATE_FORCE_FINALIZE,
            payload={
                "session_id": session_id,
                "ts": int(time.time() * 1000),
                "source": "manual_trigger"
            },
        )
        
        return {"session_id": session_id, "status": "sent", "event_type": InterviewEventType.CANDIDATE_FORCE_FINALIZE}

    def generate_question_set(
        self, 
        session_id: str | None = None, 
        invitation_id: str | None = None,
        force_regenerate: bool = False
    ) -> AIInterviewQuestionGenerateResult:
        """生成或获取面试题目集。支持通过 session_id 或 invitation_id。"""
        context_id = session_id or invitation_id
        if not context_id:
            raise ValueError("Either session_id or invitation_id must be provided")

        # 1. 尝试获取现有题目
        if not force_regenerate:
            existing = self._session_repository.get_latest_question_set(
                session_id=session_id, 
                invitation_id=invitation_id
            )
            if existing:
                return AIInterviewQuestionGenerateResult(
                    session_id=context_id,
                    version=existing.version,
                    question_count=len(existing.questions_json),
                    source=existing.source,
                    questions=existing.questions_json or [],
                )

        # 2. 获取业务基础数据
        if session_id:
            session_entity = self._session_repository.get(session_id)
            candidate_id = session_entity.candidate_id
            job_id = session_entity.job_id
            language = session_entity.language
        else:
            invitation_entity = self._invitation_repository.get_by_id(invitation_id)
            candidate_id = invitation_entity.candidate_id
            job_id = invitation_entity.job_id
            language = "zh-CN"

        candidate = self._candidate_repository.get(candidate_id)
        job = self._job_repository.get(job_id)

        # 3. 执行生成
        questions, mode = self._generate_questions_with_fallback(
            session_id=context_id,
            job_title=job.title or "",
            resume_text=candidate.resume_text or "",
            job_requirements=job.requirements or "",
            skills=(candidate.raw_profile or {}).get("skills", []),
            question_count=14,
            language=language
        )

        # 4. 保存
        version = self._session_repository.get_latest_question_set_version(session_id) + 1 if session_id else 1
        entity = self._session_repository.create_question_set(
            session_id=session_id,
            invitation_id=invitation_id,
            version=version,
            source=f"{mode}:invitation" if invitation_id else mode,
            questions=questions
        )

        return AIInterviewQuestionGenerateResult(
            session_id=context_id,
            version=entity.version,
            question_count=len(entity.questions_json),
            source=entity.source,
            questions=entity.questions_json or [],
        )

    def prebuild_question_pack(self, payload: AIInterviewQuestionPackPrebuildRequest) -> dict:
        """预生成题包并缓存到运行时存储。"""
        candidate = self._candidate_repository.get(payload.candidate_id)
        job = self._job_repository.get(payload.job_id)
        resume_text = candidate.resume_text or ""
        job_requirements = job.requirements or ""
        skills = (candidate.raw_profile or {}).get("skills", [])
        
        questions, generation_mode = self._generate_questions_with_fallback(
            session_id=f"prebuild:{payload.candidate_id}:{payload.job_id}",
            job_title=job.title or "",
            resume_text=resume_text,
            job_requirements=job_requirements,
            skills=skills,
            question_count=payload.question_count,
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
        
        question_pack = normalize_question_pack({
            PayloadKey.CANDIDATE_ID: payload.candidate_id,
            PayloadKey.JOB_ID: payload.job_id,
            "language": payload.language,
            "source": payload.source,
            "questions": questions,
            "resume_hash": resume_hash,
        })
        
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
            "generation_mode": generation_mode,
        }

    def _generate_questions_with_fallback(
        self,
        *,
        session_id: str,
        job_title: str,
        resume_text: str,
        job_requirements: str,
        skills: list[str],
        question_count: int,
        language: str = "zh-CN",
    ) -> tuple[list[dict], str]:
        """优先使用 LLM 生成题目，仅在 LLM 异常或题目不足时回退到规则驱动。"""
        llm_questions = []
        llm_enabled = self._is_interview_llm_enabled()
        logger.info(
            "ai_interview.question_generation_start session_id=%s llm_enabled=%s question_count=%s language=%s",
            session_id,
            llm_enabled,
            question_count,
            language,
        )

        if llm_enabled:
            try:
                llm_questions = self._build_questions_with_llm(
                    session_id=session_id,
                    job_title=job_title,
                    resume_text=resume_text,
                    job_requirements=job_requirements,
                    skills=skills,
                    question_count=question_count,
                    language=language,
                )
                logger.info(
                    "ai_interview.llm_question_generation_result session_id=%s llm_question_count=%s threshold=%s",
                    session_id,
                    len(llm_questions),
                    max(3, question_count // 2),
                )
                # 如果 LLM 生成了足够的题目，直接使用 LLM 结果
                if len(llm_questions) >= max(3, question_count // 2):
                    return list(llm_questions), "llm"
            except Exception as e:
                logger.error(f"ai_interview.llm_question_generation_failed session_id={session_id} error={e}", exc_info=True)
        else:
            logger.info(
                "ai_interview.llm_question_generation_skipped session_id=%s reason=llm_disabled",
                session_id,
            )

        # 回退逻辑：生成规则题目
        rule_questions = self._build_questions(
            resume_text=resume_text,
            job_requirements=job_requirements,
            skills=skills,
            question_count=question_count,
            language=language,
        )

        # 如果有部分 LLM 题目但不足，尝试混合（增强版）
        if llm_questions:
            try:
                merged = self._merge_question_candidates(
                    rule_questions=rule_questions,
                    llm_questions=llm_questions,
                    question_count=question_count,
                    resume_text=resume_text,
                    job_requirements=job_requirements,
                    skills=skills,
                    language=language,
                )
                return list(merged), "llm_hybrid"
            except Exception as e:
                logger.error(f"ai_interview.question_merge_failed session_id={session_id} error={e}")
                return list(llm_questions) if len(llm_questions) >= 3 else list(rule_questions), "llm_hybrid_fallback"

        # 完全规则回退
        logger.warning(
            "ai_interview.question_generation_fallback_rule session_id=%s llm_enabled=%s llm_question_count=%s",
            session_id,
            llm_enabled,
            len(llm_questions),
        )
        return list(rule_questions), "rule_fallback"

    def _build_questions_with_llm(
        self,
        *,
        session_id: str,
        job_title: str,
        resume_text: str,
        job_requirements: str,
        skills: list[str],
        question_count: int,
        language: str = "zh-CN",
    ) -> list[dict]:
        """使用 LLM (v4) 生成结构化面试题目，采用更稳建的正则解析方式。"""
        route = self._llm_client._router.resolve_route(PromptTaskKey.INTERVIEW_QUESTION_SET)
        logger.info(
            "ai_interview.llm_question_generation_route session_id=%s provider=%s model=%s timeout=%s retries=%s",
            session_id,
            route.provider,
            route.model_name,
            route.timeout_seconds,
            route.max_retries,
        )
        template = self._resolve_prompt_template(
            task_key=PromptTaskKey.INTERVIEW_QUESTION_SET,
            default_version="v4"
        )
        rendered = template.render(
            language=language,
            job_title=job_title,
            job_requirements=job_requirements,
            resume_text=resume_text[:4000],
            skills=skills or [],
            question_count=question_count,
        )

        context = InvokeContext(
            task_key=PromptTaskKey.INTERVIEW_QUESTION_SET,
            trace_id=f"intv-gen-{session_id}-{uuid.uuid4().hex[:6]}",
            prompt=f"{template.system_prompt}\n{rendered}",
            entity_type="session",
            entity_id=session_id,
        )

        # 采用文本模式调用，绕过 Pydantic 契约限制（v4 模板字段多于契约定义）
        response = self._llm_client.invoke(context)
        raw_text = response.content.get("text", "") if response.content else ""
        
        if not raw_text:
            logger.warning(f"ai_interview.llm_questions_empty_response session_id={session_id}")
            return []

        questions = self._parse_questions_from_llm_text(raw_text=raw_text, session_id=session_id)
        if not questions:
            logger.warning(
                "ai_interview.llm_questions_parse_empty session_id=%s raw_preview=%s",
                session_id,
                raw_text[:300].replace("\n", "\\n"),
            )
            return []

        # 标准化题目格式，保留 LLM 生成的额外业务字段
        normalized = []
        for item in questions:
            q = self._normalize_question_item(item)
            if q:
                # 保留 LLM 输出中可能包含的、但标准归一化逻辑未涵盖的字段 (如 module, role_type 等)
                if isinstance(item, dict):
                    q.update({k: v for k, v in item.items() if k not in q})
                normalized.append(q)

        logger.info(
            "ai_interview.llm_questions_generated session_id=%s count=%s first_q=%s",
            session_id,
            len(normalized),
            normalized[0]["question"][:50] if normalized else "None",
        )

        return normalized

    def _parse_questions_from_llm_text(self, *, raw_text: str, session_id: str) -> list[dict]:
        """Parse question candidates from LLM free-form text."""
        text = str(raw_text or "").strip()
        if not text:
            return []

        candidates: list[str] = [text]
        fence_matches = re.findall(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
        for block in fence_matches:
            block_text = str(block or "").strip()
            if block_text:
                candidates.append(block_text)

        first_obj = text.find("{")
        last_obj = text.rfind("}")
        if first_obj >= 0 and last_obj > first_obj:
            candidates.append(text[first_obj : last_obj + 1])

        first_arr = text.find("[")
        last_arr = text.rfind("]")
        if first_arr >= 0 and last_arr > first_arr:
            candidates.append(text[first_arr : last_arr + 1])

        seen: set[str] = set()
        for candidate in candidates:
            payload = candidate.strip()
            if not payload or payload in seen:
                continue
            seen.add(payload)
            try:
                parsed = json.loads(payload)
            except Exception:
                continue
            if isinstance(parsed, dict):
                questions = parsed.get("questions")
                if not questions:
                    for v in parsed.values():
                        if isinstance(v, list) and v and all(isinstance(item, dict) for item in v):
                            questions = v
                            break
                if isinstance(questions, list):
                    return [item for item in questions if isinstance(item, dict)]
            elif isinstance(parsed, list):
                if parsed and all(isinstance(item, dict) for item in parsed):
                    return [item for item in parsed if isinstance(item, dict)]

        line_questions: list[dict] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            match = re.match(r"^(?:\d+[\).、]\s*|[-*]\s+)(.+)$", stripped)
            if not match:
                continue
            question_text = match.group(1).strip()
            if len(question_text) < 6:
                continue
            line_questions.append({"question": question_text})
            if len(line_questions) >= 14:
                break

        if line_questions:
            logger.info(
                "ai_interview.llm_questions_parsed_from_lines session_id=%s count=%s",
                session_id,
                len(line_questions),
            )
        else:
            logger.error("ai_interview.llm_questions_parse_failed session_id=%s", session_id)
        return line_questions
    def _is_interview_llm_enabled(self) -> bool:
        """Determine whether the interview LLM flow is enabled."""
        if bool(self._settings.ai_interview_llm_enabled):
            return True
        return self._runtime_repository.is_feature_enabled(
            feature_key="ai_interview_llm",
            default_enabled=self._settings.ai_interview_llm_enabled,
        )

    def get_report(
        self,
        session_id: str,
        *,
        run_id: str | None = None,
        force_recompute: bool = False,
    ) -> AIInterviewReportResponse:
        """鏌ヨ浼氳瘽鎶ュ憡锛屾敮鎸?run_id 澶嶇畻涓庡洖鏀俱€?"""
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
            run_id=str((report_entity.payload or {}).get(PayloadKey.RUN_ID, resolved_run_id)),
        )

    def get_replay(self, session_id: str, *, limit: int = 50, offset: int = 0) -> AIInterviewReplayResponse:
        """杩斿洖浼氳瘽鍥炴斁鏁版嵁锛屾敮鎸佹寜 turn 绮掑害瀹氫綅銆?"""
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
        """鑱氬悎 handoff/blocked/latency 鎸囨爣骞剁粰鍑哄憡璀﹀師鍥犮€?"""
        sessions = self._session_repository.list_sessions(window_minutes=window_minutes)
        total = len(sessions)
        handoff_count = sum(1 for item in sessions if item.status == InterviewSessionStatus.FAILED and (item.payload or {}).get(PayloadKey.HANDOFF_REASON))
        blocked_count = sum(1 for item in sessions if item.status == InterviewSessionStatus.FAILED and (item.payload or {}).get(PayloadKey.BLOCKED_REASON))
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
            breakdown = (item.payload or {}).get(PayloadKey.LATENCY_BREAKDOWN, {})
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
            followup = str((item.payload or {}).get(PayloadKey.FOLLOWUP_QUESTION) or "").strip()
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

    def _build_turn_timeline_breakdown(self, *, session_id: str, seq: int) -> dict[str, int]:
        markers = _get_duplex_timeline_markers(session_id=session_id, seq=seq)
        if not markers:
            return {}
        breakdown: dict[str, int] = dict(markers)
        end_of_speech_at_ms = markers.get("end_of_speech_at_ms")
        asr_first_partial_at_ms = markers.get("asr_first_partial_at_ms")
        asr_final_at_ms = markers.get("asr_final_at_ms")
        llm_first_token_at_ms = markers.get("llm_first_token_at_ms")
        tts_first_pcm_at_ms = markers.get("tts_first_pcm_at_ms")
        client_first_play_at_ms = markers.get("client_first_play_at_ms")

        if end_of_speech_at_ms and asr_first_partial_at_ms:
            breakdown["asr_first_partial_ms"] = max(0, asr_first_partial_at_ms - end_of_speech_at_ms)
        if end_of_speech_at_ms and asr_final_at_ms:
            breakdown["end_of_speech_to_asr_final_ms"] = max(0, asr_final_at_ms - end_of_speech_at_ms)
        if asr_final_at_ms and llm_first_token_at_ms:
            breakdown["llm_first_token_ms"] = max(0, llm_first_token_at_ms - asr_final_at_ms)
        if tts_first_pcm_at_ms:
            tts_anchor_at_ms = llm_first_token_at_ms or asr_final_at_ms or end_of_speech_at_ms
            if tts_anchor_at_ms:
                breakdown["tts_first_packet_ms"] = max(0, tts_first_pcm_at_ms - tts_anchor_at_ms)
        if client_first_play_at_ms and tts_first_pcm_at_ms:
            breakdown["client_first_play_ms"] = max(0, client_first_play_at_ms - tts_first_pcm_at_ms)
        return breakdown

    def record_client_playback_mark(
        self,
        *,
        session_id: str,
        seq: int,
        packet_index: int | None = None,
        client_ts_ms: int | None = None,
        transport: str | None = None,
    ) -> dict[str, int | str]:
        entity = self._session_repository.get(session_id)
        played_at_ms = _record_duplex_timeline_marker(
            session_id=session_id,
            seq=seq,
            marker_key="client_first_play_at_ms",
            at_ms=client_ts_ms,
        )
        markers = self._build_turn_timeline_breakdown(session_id=session_id, seq=seq)
        self._event_repository.create(
            event_type="ai_interview.rtc.client_playback",
            entity_type="ai_interview_session",
            entity_id=session_id,
            status="success",
            operator="candidate_client",
            session_id=session_id,
            job_id=entity.job_id,
            payload={
                "seq": seq,
                "packet_index": packet_index,
                "client_first_play_at_ms": played_at_ms,
                "transport": transport or "binary",
                PayloadKey.LATENCY_BREAKDOWN: markers,
            },
        )
        return {
            "session_id": session_id,
            "seq": int(seq),
            "client_first_play_at_ms": int(played_at_ms),
        }

    def rtc_join(self, session_id: str, payload: AIInterviewRTCJoinRequest) -> AIInterviewRTCJoinResponse:
        """RTC-001锛氬€欓€変汉鍏ヤ細锛屾敮鎸佸悗缁噸杩炪€?"""
        entity = self._session_repository.get(session_id)
        self._ensure_session_active_for_realtime(entity, action="rtc_join")
        if payload.candidate_id != entity.candidate_id:
            raise InvalidStateError("candidate_id 涓庝細璇濅笉鍖归厤")
        join_info = self._rtc_gateway.join_room(
            session_id=session_id,
            room_id=entity.rtc_room_id,
            client_id=payload.client_id,
            candidate_id=payload.candidate_id,
            join_token=entity.join_token,
        )
        updated_entity = self._session_repository.update_status(
            session_id,
            status=entity.status,
            payload_patch={
                "rtc_client_id": payload.client_id,
                "rtc_joined": True,
                **self._build_rtc_payload(join_info),
            },
        )
        ten_patch = self._prepare_ten_runtime(updated_entity, rtc_override=join_info)
        if ten_patch:
            updated_entity = self._session_repository.update_status(
                session_id,
                status=updated_entity.status,
                payload_patch=ten_patch,
            )
            updated_entity = self._maybe_auto_launch_ten(updated_entity)
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
            provider=join_info.vendor,
            room_id=join_info.room_id,
            channel_name=join_info.channel_name or join_info.room_id,
            join_token=join_info.join_token,
            app_id=join_info.app_id,
            uid=join_info.uid,
            expire_at=join_info.expire_at,
            reconnectable=True,
            transport=join_info.transport,
        )

    def get_ten_runtime_config(self, session_id: str) -> AIInterviewTENRuntimeResponse:
        entity = self._session_repository.get(session_id)
        self._ensure_session_active_for_realtime(entity, action="ten_runtime_config")
        response = AIInterviewTENRuntimeResponse.model_validate(self._build_ten_runtime_response(entity))
        if response.launch_command:
            print(
                f"[TEN-CMD] session={session_id} status={response.launch_status}\n{response.launch_command}",
                flush=True,
            )
        else:
            print(
                f"[TEN-CMD] session={session_id} status={response.launch_status} command=<empty>",
                flush=True,
            )
        return response

    def launch_ten_session(self, session_id: str) -> AIInterviewTENRuntimeResponse:
        entity = self._session_repository.get(session_id)
        self._ensure_session_active_for_realtime(entity, action="ten_launch")
        ten_patch = self._prepare_ten_runtime(entity)
        if ten_patch:
            entity = self._session_repository.update_status(session_id, status=entity.status, payload_patch=ten_patch)
        property_file = str((entity.payload or {}).get("ten_property_file") or "")
        launch_patch = self._ten_runtime_manager.launch_session(session_id=session_id, property_file=property_file)
        entity = self._session_repository.update_status(session_id, status=entity.status, payload_patch=launch_patch)
        response = AIInterviewTENRuntimeResponse.model_validate(self._build_ten_runtime_response(entity))
        print(
            f"[TEN-CMD] launch session={session_id} status={response.launch_status}\n{response.launch_command or ''}",
            flush=True,
        )
        return response

    def rtc_reconnect(self, session_id: str, payload: AIInterviewRTCReconnectRequest) -> AIInterviewRTCReconnectResponse:
        """RTC-001锛氭柇绾块噸杩炪€?"""
        entity = self._session_repository.get(session_id)
        self._ensure_session_active_for_realtime(entity, action="rtc_reconnect")
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

    @staticmethod
    def _ensure_session_active_for_realtime(entity, *, action: str) -> None:
        if entity.status not in {InterviewSessionStatus.CREATED, InterviewSessionStatus.IN_PROGRESS}:
            raise InvalidStateError(
                f"AI interview session '{entity.id}' cannot perform '{action}' from status '{entity.status}'. "
                "Please create a new session for a new interview."
            )

    def rtc_subscribe_audio(self, session_id: str, payload: AIInterviewRTCAudioSubscribeRequest) -> AIInterviewRTCAudioSubscribeResponse:
        """RTC-001D锛氳闃呭€欓€変汉闊宠建锛屾敮鎸佸紑鍏抽檷绾с€?"""
        entity = self._session_repository.get(session_id)
        if payload.candidate_id != entity.candidate_id:
            raise InvalidStateError("candidate_id 涓庝細璇濅笉鍖归厤")

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
        """RTC-004锛氬€欓€変汉瑙嗛涓婅绛栫暐涓?AI 璁㈤槄/褰曞埗绛栫暐搴旂敤銆?"""
        entity = self._session_repository.get(session_id)
        if payload.candidate_id != entity.candidate_id:
            raise InvalidStateError("candidate_id 涓庝細璇濅笉鍖归厤")

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
            raise InvalidStateError(f"room_id '{payload.room_id}' 鏈叧鑱斾换浣?AI 闈㈣瘯浼氳瘽")

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
                speaker=SpeakerRole.CANDIDATE,
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
            followup_question = str((event_result or {}).get(PayloadKey.FOLLOWUP_QUESTION) or "").strip()
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
        """RTC-002锛欰SR 娴佸紡閫傞厤锛岃繑鍥炶浆鍐欑粨鏋滃苟钀藉簱銆?"""
        entity = self._session_repository.get(session_id)
        audio_bytes = getattr(payload, "audio_bytes", None)
        if self._settings.asr_force_streaming and not (payload.audio_base64 or audio_bytes) and not payload.is_final:
            raise InvalidStateError("ASR force_streaming 宸插紑鍚紝闊抽鏁版嵁涓嶅彲涓虹┖")
        if payload.chunk_index > payload.chunk_total:
            raise InvalidStateError("chunk_index 涓嶈兘澶т簬 chunk_total")
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
            speaker=SpeakerRole.CANDIDATE if payload.is_final else SpeakerRole.CANDIDATE_PARTIAL,
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
                PayloadKey.LATENCY_BREAKDOWN: latency_breakdown,
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
                PayloadKey.LATENCY_BREAKDOWN: latency_breakdown,
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
                    "speaker": SpeakerRole.CANDIDATE if payload.is_final else SpeakerRole.CANDIDATE_PARTIAL,
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
        """RTC-003锛歍TS 娴佸紡鎾姤锛岃繑鍥炲垎鐗囦笌闊抽鍦板潃銆?"""
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
                    event_type=InterviewEventType.TTS_PACKET,
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
                PayloadKey.LATENCY_BREAKDOWN: latency_breakdown,
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
                PayloadKey.VOICE: payload.voice,
                "chunk_count": len(tts_result.chunks),
                "provider": tts_result.provider,
                "published": published,
                "publish_mode": publish_mode,
                "track_sid": track_sid,
                "bot_identity": bot_identity,
                "target_latency_ms": payload.target_latency_ms,
                "realtime_target_met": realtime_target_met,
                PayloadKey.LATENCY_BREAKDOWN: latency_breakdown,
            },
        )
        DEFAULT_INTERVIEW_EVENT_BUS.publish(
            session_id=session_id,
            event_type="tts.ready",
            payload={
                "text": text,
                PayloadKey.VOICE: payload.voice,
                "audio_uris": list(tts_result.audio_uris),
                "published": published,
                PayloadKey.LATENCY_BREAKDOWN: latency_breakdown,
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
        voice: str = DEFAULT_TTS_VOICE,
        chunk_size: int = 24,
    ):
        """娴佸紡鐢熸垚 TTS 鍖咃紝鐢ㄤ簬 duplex 棣栧寘浼樺厛鎺ㄩ€併€?"""
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
        payload = dict(payload or {})
        client_ts_ms = payload.get("client_ts_ms")
        safe_client_ts_ms = int(client_ts_ms) if isinstance(client_ts_ms, (int, float)) else None
        end_of_speech_at_ms = _record_duplex_timeline_marker(
            session_id=session_id,
            seq=seq,
            marker_key="end_of_speech_at_ms",
            at_ms=safe_client_ts_ms,
        )
        logger.info(f"[Duplex] Explicit end_of_turn received: session={session_id} seq={seq} frame_id={frame_id}")
        self._safe_flush_asr(session_id, seq=seq)
        return {
            "status": "accepted",
            "session_id": session_id,
            "seq": seq,
            "end_of_speech_at_ms": int(end_of_speech_at_ms),
        }

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
            _record_duplex_timeline_marker(
                session_id=session_id,
                seq=max(1, seq),
                marker_key="asr_final_at_ms",
            )
            
            # CRITICAL: Trigger the interview logic if we got a final transcript
            is_final_resp = (asr_resp.asr_meta or {}).get("is_final") or False
            if is_final_resp and (asr_resp.transcript or "").strip():
                event_req = AIInterviewSessionEventRequest(
                    event_id=f"eot-flush-{uuid.uuid4().hex[:8]}",
                    seq=max(1, seq),
                    speaker=SpeakerRole.CANDIDATE,
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
        """鍏ㄥ弻宸ュ疄鏃堕煶棰戝垎鐗囧鐞嗭細ASR -> 浜嬩欢鍥炲啓(鍙€? -> 杩介棶/闊抽杈撳嚭銆?"""
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
            _record_duplex_timeline_marker(
                session_id=session_id,
                seq=seq,
                marker_key="asr_final_at_ms",
            )
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
                _record_duplex_timeline_marker(
                    session_id=session_id,
                    seq=seq,
                    marker_key="asr_first_partial_at_ms",
                )
                DEFAULT_INTERVIEW_EVENT_BUS.publish(
                    session_id=session_id,
                    event_type="asr.turn",
                    payload={
                        "event_id": f"asr-turn-{session_id}-{seq}-{chunk_index}",
                        "turn_id": None,
                        "speaker": SpeakerRole.CANDIDATE_PARTIAL,
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
                        "prefetched_followup_question": prefetched[PayloadKey.FOLLOWUP_QUESTION],
                        "prefetched_llm_ms": int(prefetched.get("llm_prefetch_ms") or 0),
                        "prefetched_from_partial": True,
                    }
                )
            event_req = AIInterviewSessionEventRequest(
                event_id=f"duplex-turn-{session_id}-{seq}",
                seq=seq,
                speaker=SpeakerRole.CANDIDATE,
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
            has_punctuation = any(p in normalized for p in ("。", "，", "；", ".", "?", "!"))
            if not is_final and (
                (len(normalized) >= 4 and has_punctuation) or 
                (len(normalized) >= 20) # Fallback for unpunctuated streams
            ):
                logger.info(f"Triggering TENTATIVE execution for session={session_id} seq={seq} transcript='{normalized}'")
                stage = InterviewStageGroup.CORE
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
            stage = InterviewStageGroup.CORE
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
                    seq=seq,
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
                    PayloadKey.FOLLOWUP_QUESTION: followup,
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
        """杩愯鍚庡彴瀹炴椂缂栨帓锛堜笉鍐欐暟鎹簱锛夈€?"""
        from ..db.session import SessionLocal
        with SessionLocal() as session:
            worker_service = get_ai_interview_service(session)
            try:
                # This worker only handles TTS playback. 
                def _on_audio_packet(packet: dict) -> None:
                    if abort_event and abort_event.is_set():
                        return
                    if packet.get("audio_bytes") and not packet.get("_first_pcm_marker_recorded"):
                        packet["tts_first_pcm_at_ms"] = _record_duplex_timeline_marker(
                            session_id=session_id,
                            seq=seq,
                            marker_key="tts_first_pcm_at_ms",
                        )
                        packet["_first_pcm_marker_recorded"] = True
                    DEFAULT_INTERVIEW_EVENT_BUS.publish(
                        session_id=session_id,
                        event_type=InterviewEventType.TTS_PACKET,
                        payload={
                            PayloadKey.VOICE: DEFAULT_TTS_VOICE,
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
                     prefetched_followup = cached.get(PayloadKey.FOLLOWUP_QUESTION)

                def llm_stream_wrapper(t, c, s, l):
                    return worker_service._build_followup_question_with_llm(
                        session_id=session_id,
                        seq=seq,
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

    def _build_rtc_payload(self, rtc_info) -> dict:
        payload = {
            "rtc_vendor": rtc_info.vendor,
            "rtc_transport": rtc_info.transport,
            "rtc_app_id": rtc_info.app_id,
            "rtc_channel_name": rtc_info.channel_name or rtc_info.room_id,
            "rtc_uid": rtc_info.uid,
        }
        if rtc_info.expire_at is not None:
            payload["rtc_token_expire_at"] = self._serialize_datetime(rtc_info.expire_at)
        metadata = dict(rtc_info.metadata or {})
        if metadata.get("ten_bot_uid"):
            payload["ten_agent_user_id"] = metadata["ten_bot_uid"]
        if metadata.get("ten_bot_token"):
            payload["ten_agent_token"] = metadata["ten_bot_token"]
        if metadata.get("ten_bot_expire_at"):
            payload["ten_agent_token_expire_at"] = metadata["ten_bot_expire_at"]
        return {key: value for key, value in payload.items() if value is not None}

    def _prepare_ten_runtime(self, entity, rtc_override=None) -> dict:
        rtc_block = self._build_rtc_dict(entity, rtc_override=rtc_override)
        if not rtc_block.get("app_id") or not rtc_block.get("channel_name"):
            return {}
        candidate = self._candidate_repository.get(entity.candidate_id)
        job = self._job_repository.get(entity.job_id)
        job_requirements = str(job.requirements or "").strip()
        runtime_payload = dict(entity.payload or {})
        runtime_payload.update(
            self._build_runtime_company_payload(
                job_id=entity.job_id,
                job_requirements=job_requirements,
                payload=runtime_payload,
            )
        )
        runtime_payload.update(
            self._build_runtime_resume_payload(
                candidate_name=str(candidate.name or "").strip(),
                resume_text=str(candidate.resume_text or "").strip(),
                job_requirements=job_requirements,
            )
        )
        runtime_payload.update(
            self._build_runtime_question_pack_payload(
                session_id=entity.id,
                payload=runtime_payload,
            )
        )
        return self._ten_runtime_manager.prepare_session(
            session_id=entity.id,
            candidate_id=entity.candidate_id,
            job_id=entity.job_id,
            language=entity.language,
            rtc={
                **rtc_block,
                "ten_bot_user_id": str((entity.payload or {}).get("ten_agent_user_id") or rtc_block.get("ten_bot_user_id") or ""),
                "ten_bot_token": str((entity.payload or {}).get("ten_agent_token") or rtc_block.get("ten_bot_token") or ""),
            },
            payload=runtime_payload,
        )

    @staticmethod
    def _build_runtime_resume_payload(
        *,
        candidate_name: str,
        resume_text: str,
        job_requirements: str,
    ) -> dict[str, str]:
        compact_resume = " ".join((resume_text or "").split())
        if len(compact_resume) > 1200:
            compact_resume = compact_resume[:1200]
        if not compact_resume:
            compact_resume = "候选人简历信息暂缺。"
        if candidate_name:
            compact_resume = f"{candidate_name}：{compact_resume}"
        return {
            "resume_summary": compact_resume,
            "job_requirements": (job_requirements or "").strip(),
        }

    def _build_runtime_question_pack_payload(
        self,
        *,
        session_id: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        merged_payload = dict(payload or {})
        raw_question_pack = merged_payload.get("question_pack")
        if isinstance(raw_question_pack, dict):
            normalized_pack = normalize_question_pack(raw_question_pack)
            if normalized_pack.get("questions"):
                return {
                    "question_pack": normalized_pack,
                    "question_pack_source": str(
                        merged_payload.get("question_pack_source")
                        or normalized_pack.get("source")
                        or "payload"
                    ).strip(),
                    "question_pack_version": (
                        merged_payload.get("question_pack_version")
                        or normalized_pack.get("version")
                        or ""
                    ),
                }

        cached_pack = self._runtime_store.get_question_pack(session_id=session_id)
        if isinstance(cached_pack, dict) and cached_pack.get("questions"):
            normalized_pack = normalize_question_pack(cached_pack)
            return {
                "question_pack": normalized_pack,
                "question_pack_source": str(
                    merged_payload.get("question_pack_source")
                    or normalized_pack.get("source")
                    or "runtime_store"
                ).strip(),
                "question_pack_version": (
                    merged_payload.get("question_pack_version")
                    or normalized_pack.get("version")
                    or ""
                ),
            }

        existing = self._get_existing_question_set(session_id=session_id)
        if existing and existing.get("questions"):
            normalized_pack = normalize_question_pack(existing)
            return {
                "question_pack": normalized_pack,
                "question_pack_source": str(
                    merged_payload.get("question_pack_source")
                    or normalized_pack.get("source")
                    or "question_set"
                ).strip(),
                "question_pack_version": (
                    merged_payload.get("question_pack_version")
                    or normalized_pack.get("version")
                    or ""
                ),
            }
        return {}

    def _build_runtime_company_payload(
        self,
        *,
        job_id: str,
        job_requirements: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, str]:
        merged_payload = dict(payload or {})
        explicit_company_info = str(
            merged_payload.get("company_info")
            or merged_payload.get("company_profile")
            or merged_payload.get("company_intro")
            or ""
        ).strip()
        if explicit_company_info:
            return {
                "company_info": explicit_company_info,
                "company_info_source": "payload",
                "company_info_version": "runtime_v1",
            }

        fallback_company_info = self._load_company_info_fallback(
            job_id=job_id,
            job_requirements=job_requirements,
        )
        if fallback_company_info:
            return {
                "company_info": fallback_company_info,
                "company_info_source": "dev_file_fallback",
                "company_info_version": "runtime_v1",
            }
        return {}

    def _load_company_info_fallback(self, *, job_id: str, job_requirements: str) -> str:
        if str(self._settings.environment or "").strip().lower() not in {"dev", "development"}:
            return ""

        candidate_paths = [
            Path(__file__).resolve().parents[2] / "data" / "company_info.txt",
            Path("d:/24985/code/boss-cli-main/AI-HR/data/company_info.txt"),
        ]
        for path in candidate_paths:
            try:
                if path.exists():
                    text = path.read_text(encoding="utf-8").strip()
                    if text:
                        return text
            except Exception:
                logger.warning("ai_interview.company_info_fallback_read_failed path=%s", path)

        if job_requirements.strip():
            return f"宀椾綅鐩稿叧淇℃伅鍙傝€冿細{job_requirements.strip()[:220]}"
        if job_id:
            logger.warning("ai_interview.company_info_missing job_id=%s", job_id)
        return ""

    def _build_rtc_dict(self, entity, rtc_override=None) -> dict:
        base = self._build_rtc_payload(rtc_override) if rtc_override is not None else dict(entity.payload or {})
        return {
            "provider": str(base.get("rtc_vendor") or self._rtc_gateway.provider_name),
            "transport": str(base.get("rtc_transport") or self._settings.rtc_default_transport),
            "room_id": entity.rtc_room_id,
            "channel_name": str(base.get("rtc_channel_name") or entity.rtc_room_id),
            "token": entity.join_token,
            "app_id": base.get("rtc_app_id"),
            "uid": base.get("rtc_uid"),
            "expire_at": self._parse_datetime(base.get("rtc_token_expire_at")),
            "ten_bot_user_id": base.get("ten_agent_user_id"),
            "ten_bot_token": base.get("ten_agent_token"),
        }

    def _build_ten_runtime_response(self, entity) -> dict:
        rtc = self._build_rtc_dict(entity)
        payload = dict(entity.payload or {})
        return {
            "session_id": entity.id,
            "enabled": bool(payload.get("ten_enabled")),
            "room_id": entity.rtc_room_id,
            "provider": rtc["provider"],
            "app_id": rtc.get("app_id"),
            "channel_name": rtc.get("channel_name"),
            "agent_user_id": payload.get("ten_agent_user_id"),
            "remote_user_id": payload.get("ten_remote_user_id") or rtc.get("uid"),
            "property_file": payload.get("ten_property_file"),
            "launch_status": str(payload.get("ten_launch_status") or ("disabled" if not payload.get("ten_enabled") else "prepared")),
            "launch_command": payload.get("ten_launch_command"),
            "process_pid": payload.get("ten_process_pid"),
        }

    def _maybe_auto_launch_ten(self, entity):
        if not self._settings.ai_interview_ten_auto_launch:
            return entity
        property_file = str((entity.payload or {}).get("ten_property_file") or "")
        if not property_file:
            return entity
        current_status = str((entity.payload or {}).get("ten_launch_status") or "")
        if current_status == "launched":
            return entity
        launch_patch = self._ten_runtime_manager.launch_session(session_id=entity.id, property_file=property_file)
        return self._session_repository.update_status(entity.id, status=entity.status, payload_patch=launch_patch)

    @staticmethod
    def _serialize_datetime(value: datetime | str | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return value.isoformat()

    @staticmethod
    def _parse_datetime(value: str | datetime | None) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    def _to_session_dict(self, entity) -> dict:
        """灏嗕細璇濆疄浣撹浆鎹负缁熶竴鍝嶅簲缁撴瀯銆?"""
        join_url = f"/interview/{entity.id}?token={entity.join_token}"
        rtc = self._build_rtc_dict(entity)
        ten = self._build_ten_runtime_response(entity)
        return {
            "id": entity.id,
            PayloadKey.CANDIDATE_ID: entity.candidate_id,
            PayloadKey.JOB_ID: entity.job_id,
            "status": entity.status,
            "channel": entity.channel,
            "language": entity.language,
            "rtc_room_id": entity.rtc_room_id,
            "join_token": entity.join_token,
            "join_url": join_url,
            "rtc": rtc,
            "ten": {
                "enabled": ten["enabled"],
                "room_id": ten["room_id"],
                "agent_user_id": ten["agent_user_id"],
                "remote_user_id": ten["remote_user_id"],
                "property_file": ten["property_file"],
                "launch_status": ten["launch_status"],
                "launch_command": ten["launch_command"],
            },
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
        """鏍规嵁杩愯鏃跺紑鍏宠В鏋?AI 闈㈣瘯杩愯妯″紡銆?"""
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
        """鍔犺浇浼氳瘽杩愯鎬侊紝涓嶅瓨鍦ㄥ垯鍒濆鍖栥€?"""
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

    def _reset_runtime_state_for_start(self, *, session_id: str, question_pack: dict) -> dict:
        """Force a clean runtime state for every newly started interview session."""

        initial = self._question_flow_engine.init_state(question_pack=question_pack)
        self._runtime_store.init_session_state(
            session_id=session_id,
            state=initial,
            ttl_seconds=int(self._settings.ai_interview_state_ttl_seconds),
        )
        return initial

    def _refresh_runtime_question_pack_for_start(self, *, session_id: str) -> dict | None:
        """Hydrate the latest session-scoped question pack into runtime store before start."""

        latest = self._session_repository.get_latest_question_set(session_id)
        if latest is not None:
            questions = [item for item in (latest.questions_json or []) if isinstance(item, dict)]
            question_pack = {
                "session_id": session_id,
                "version": int(latest.version),
                "source": str(latest.source or "session_latest"),
                "question_count": len(questions),
                "questions": questions,
            }
            self._runtime_store.save_question_pack(
                session_id=session_id,
                version=int(latest.version),
                question_pack=question_pack,
                ttl_seconds=int(self._settings.ai_interview_question_pack_ttl_seconds),
            )
            logger.info(
                "ai_interview.question_pack_refreshed_for_start session_id=%s version=%s source=%s question_count=%s question_ids=%s",
                session_id,
                question_pack.get("version"),
                question_pack.get("source"),
                question_pack.get("question_count"),
                self._summarize_question_ids(question_pack),
            )
            return question_pack
        logger.warning("ai_interview.question_pack_missing_for_start session_id=%s", session_id)
        return self._runtime_store.get_question_pack(session_id=session_id)

    def _ensure_runtime_question_pack_for_start(self, *, session_id: str) -> dict | None:
        """Ensure every started session has a session-scoped question pack."""

        question_pack = self._refresh_runtime_question_pack_for_start(session_id=session_id)
        if question_pack and question_pack.get("questions"):
            return question_pack

        session_entity = self._session_repository.get(session_id)
        candidate = self._candidate_repository.get(session_entity.candidate_id)
        job = self._job_repository.get(session_entity.job_id)
        question_count = max(1, int((session_entity.payload or {}).get("question_count") or 14))
        questions, generation_mode = self._generate_questions_with_fallback(
            session_id=session_id,
            job_title=job.title or "",
            resume_text=candidate.resume_text or "",
            job_requirements=job.requirements or "",
            skills=(candidate.raw_profile or {}).get("skills", []),
            question_count=question_count,
            language=session_entity.language,
        )
        if not questions:
            logger.warning("ai_interview.question_pack_auto_generate_empty session_id=%s", session_id)
            return None

        version = self._session_repository.get_latest_question_set_version(session_id) + 1
        source = generation_mode
        self._session_repository.create_question_set(
            session_id=session_id,
            version=version,
            source=source,
            questions=questions,
        )
        question_pack = normalize_question_pack(
            {
                "session_id": session_id,
                "version": version,
                "source": source,
                "language": session_entity.language,
                "questions": questions,
            }
        )
        self._runtime_store.save_question_pack(
            session_id=session_id,
            version=version,
            question_pack=question_pack,
            ttl_seconds=int(self._settings.ai_interview_question_pack_ttl_seconds),
        )
        logger.info(
            "ai_interview.question_pack_auto_generated_for_start session_id=%s version=%s source=%s generation_mode=%s question_count=%s question_ids=%s",
            session_id,
            version,
            source,
            generation_mode,
            question_pack.get("question_count"),
            self._summarize_question_ids(question_pack),
        )
        return question_pack

    def _log_runtime_start_snapshot(self, *, session_id: str, question_pack: dict) -> None:
        """Emit a startup snapshot for runtime pack/state verification."""

        state = self._runtime_store.get_session_state(session_id=session_id) or {}
        logger.info(
            "ai_interview.start_runtime_ready session_id=%s question_pack_version=%s question_pack_source=%s "
            "question_count=%s state_stage=%s active_question_index=%s current_question_id=%s question_ids=%s",
            session_id,
            question_pack.get("version"),
            question_pack.get("source"),
            question_pack.get("question_count"),
            state.get("interview_stage"),
            state.get("active_question_index"),
            state.get("current_question_id"),
            self._summarize_question_ids(question_pack),
        )

    @staticmethod
    def _summarize_question_ids(question_pack: dict[str, object] | None) -> str:
        questions = question_pack.get("questions", []) if isinstance(question_pack, dict) else []
        question_ids: list[str] = []
        if isinstance(questions, list):
            for item in questions[:16]:
                if not isinstance(item, dict):
                    continue
                identifier = str(item.get("idx") or item.get("question_id") or item.get("id") or "").strip()
                if identifier:
                    question_ids.append(identifier)
        return ",".join(question_ids)

    def _get_active_question_context(self, *, session_id: str) -> dict | None:
        """璇诲彇褰撳墠娲诲姩棰樼洰涓婁笅鏂囥€?"""
        question_pack = self._runtime_store.get_question_pack(session_id=session_id)
        if not question_pack:
            return None
        state = self._runtime_store.get_session_state(session_id=session_id)
        if not state:
            state = self._load_or_init_runtime_state(session_id=session_id, question_pack=question_pack)
        return self._question_flow_engine.current_question(state=state, question_pack=question_pack)

    def _advance_stage_by_question_flow(self, *, session_id: str, state: dict) -> str:
        """鏍规嵁棰樻祦鐘舵€佹帹杩涢樁娈点€?"""
        question_pack = self._runtime_store.get_question_pack(session_id=session_id) or {}
        stage = self._question_flow_engine.derive_stage(state=state, question_pack=question_pack)
        current = self._session_repository.get(session_id)
        self._session_repository.update_status(
            session_id,
            status=current.status,
            payload_patch={PayloadKey.INTERVIEW_STAGE: stage},
        )
        self._runtime_store.patch_session_state(
            session_id=session_id,
            patch={PayloadKey.INTERVIEW_STAGE: stage},
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
        """鍩轰簬鏈疆鍥炵瓟鏇存柊棰樻祦鐘舵€併€?"""
        state = self._load_or_init_runtime_state(session_id=session_id, question_pack=question_pack)
        decision = self._runtime_engine.process_candidate_turn(
            state=state,
            question_pack=question_pack,
            transcript=transcript,
            confidence=confidence,
        )
        evaluation = decision.evaluation
        updated = dict(decision.updated_state)
        updated_stage = self._question_flow_engine.derive_stage(state=updated, question_pack=question_pack)
        updated[PayloadKey.INTERVIEW_STAGE] = updated_stage
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
                PayloadKey.INTERVIEW_STAGE: updated_stage,
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
            PayloadKey.INTERVIEW_STAGE: updated_stage,
            "question_completion_rate": completion_rate,
        }

    def _attach_prebuilt_question_pack(self, *, session_id: str) -> dict[str, object]:
        """鍦ㄤ細璇濆惎鍔ㄩ樁娈靛皾璇曡杞介鐢熸垚棰樺寘銆?"""
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
        """鏋勫缓棰勭敓鎴愰鍖?key銆?"""
        normalized_lang = (language or "zh-CN").strip()
        normalized_hash = (resume_hash or "").strip()[:16]
        return f"{job_id}:{candidate_id}:{normalized_lang}:{normalized_hash}"

    @staticmethod
    def _compute_prebuild_resume_hash(*, resume_text: str, job_requirements: str, skills: list[str]) -> str:
        """璁＄畻棰勭敓鎴愰鍖呭唴瀹瑰搱甯屻€?"""
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
    def _shorten_question_text(question: str) -> str:
        """Lightly normalize question text without aggressive truncation."""

        text = re.sub(r"\s+", " ", str(question or "")).strip()
        return text

    @staticmethod
    def _normalize_stage_code(raw_stage: str, dimension: str = "") -> str:
        stage = str(raw_stage or "").strip().upper()
        if stage in {
            InterviewStage.SELF_INTRO,
            InterviewStage.TECH_STACK,
            InterviewStage.PROJECT_DEEP_DIVE,
            InterviewStage.JD_MATCH,
            InterviewStage.GENERAL_PROBE,
            InterviewStage.COMPANY_QA,
        }:
            return stage

        hint = f"{raw_stage} {dimension}".lower()
        if any(
            token in hint
            for token in ("自我介绍", "候选人画像", "经历概述", "intro", "self_intro", "introduction")
        ):
            return InterviewStage.SELF_INTRO
        if any(
            token in hint
            for token in ("椤圭洰娣辨寲", "椤圭洰缁忛獙", "ownership", "妯″潡", "鎸戞垬", "project", "tradeoff")
        ):
            return InterviewStage.PROJECT_DEEP_DIVE
        if any(token in hint for token in ("瀹炰範", "鑱岃矗", "鍗忎綔", "intern", "experience_validation")):
            return InterviewStage.JD_MATCH
        if any(
            token in hint
            for token in ("绯荤粺璁捐", "鎺掓煡", "鎬ц兘", "鏁呴殰", "system", "troubleshooting", "capability_probe")
        ):
            return InterviewStage.GENERAL_PROBE
        if any(token in hint for token in ("鍙嶉棶", "鍥㈤槦", "鍏徃浠嬬粛", "qa", "company_qa")):
            return InterviewStage.COMPANY_QA
        return InterviewStage.TECH_STACK

    @staticmethod
    def _repair_question_text(question: str, *, dimension: str, language: str = "zh-CN") -> str:
        text = str(question or "").strip()
        if not text or language == "en-US":
            return text

        interrogatives = (
            "怎么",
            "为什么",
            "如何",
            "哪些",
            "哪块",
            "哪个",
            "有没有",
            "举例",
            "结合",
            "什么",
        )
        if text.endswith(("？", "?")) and not any(token in text for token in interrogatives):
            stem = text.rstrip("？").rstrip("。")
            if stem.startswith(("你提到", "你说", "你简历里写了", "你简历里提到", "你对", "你熟悉", "你做过", "岗位要求")):
                return f"{stem}，能具体说说吗？"
        if len(text) < 14 and text.endswith(("？", "?")):
            stem = text.rstrip("？").rstrip("。")
            return f"{stem}，具体是怎么做的？"
        return text

    @staticmethod
    def _normalize_question_item(item: dict | object) -> dict | None:
        normalized = normalize_question_item(item)
        if normalized is None:
            return None
        question = AIInterviewService._shorten_question_text(str(normalized.get("question") or "").strip())
        question = AIInterviewService._repair_question_text(
            question,
            dimension=str(normalized.get("dimension") or "communication"),
            language="zh-CN",
        )
        if not question:
            return None
        normalized["question"] = question
        return normalized

    @staticmethod
    def _extract_keyword_tokens(*, skills: list[str], job_requirements: str, resume_text: str, language: str) -> set[str]:
        tokens = {str(item).strip().lower() for item in (skills or []) if str(item).strip()}
        text = f"{(job_requirements or '')[:500]} {(resume_text or '')[:500]}".lower()
        if language == "en-US":
            for token in re.findall(r"[a-z][a-z0-9_+\-.]{2,}", text):
                tokens.add(token)
        else:
            for term in ("性能", "并发", "架构", "稳定性", "排查", "数据库", "系统", "线上", "故障", "可用性", "扩展性"):
                if term in text:
                    tokens.add(term)
        return {token for token in tokens if token}

    def _score_question_item(self, *, question: dict, source: str, keyword_tokens: set[str], language: str) -> int:
        text = f"{question.get('question', '')} {question.get('expected_signal', '')} {question.get('followup_condition', '')}".lower()
        base = 70 if source == "llm" else 48
        if source == "seed":
            base += 15 # 绉嶅瓙棰樺叿鏈夐珮浼樺厛绾?
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
            if any(term in text for term in ("\u6027\u80fd", "\u5e76\u53d1", "\u67b6\u6784", "\u6392\u67e5", "\u6307\u6807", "\u5bb9\u91cf", "\u7a33\u5b9a\u6027", "\u6545\u969c", "\u6743\u8861")):
                base += 8
        return base

    @staticmethod
    def _stage_quota_plan(question_count: int) -> dict[str, int]:
        total = max(1, int(question_count or 0))
        if total >= 14:
            return {
                InterviewStage.SELF_INTRO: 1,
                InterviewStage.TECH_STACK: 8,
                InterviewStage.PROJECT_DEEP_DIVE: 2,
                InterviewStage.JD_MATCH: 1,
                InterviewStage.GENERAL_PROBE: 1,
                InterviewStage.COMPANY_QA: 1,
            }
        if total >= 12:
            return {
                InterviewStage.SELF_INTRO: 1,
                InterviewStage.TECH_STACK: 7,
                InterviewStage.PROJECT_DEEP_DIVE: 1,
                InterviewStage.JD_MATCH: 1,
                InterviewStage.GENERAL_PROBE: 1,
                InterviewStage.COMPANY_QA: 1,
            }
        if total >= 10:
            return {
                InterviewStage.SELF_INTRO: 1,
                InterviewStage.TECH_STACK: 6,
                InterviewStage.PROJECT_DEEP_DIVE: 1,
                InterviewStage.JD_MATCH: 1,
                InterviewStage.GENERAL_PROBE: 1,
            }
        return {
            InterviewStage.SELF_INTRO: 1,
            InterviewStage.TECH_STACK: max(1, total - 3),
            InterviewStage.PROJECT_DEEP_DIVE: 1,
            InterviewStage.GENERAL_PROBE: 1,
        }

    @staticmethod
    def _question_bucket(question: dict) -> str:
        bucket = str(question.get("bucket") or "").strip().lower()
        if bucket in {"profile", "stack", "scenario", "experience", "wrap_up"}:
            return bucket
        stage = str(question.get("stage") or InterviewStage.TECH_STACK).strip()
        dimension = str(question.get("dimension") or "").strip().lower()
        if stage == InterviewStage.SELF_INTRO:
            return "profile"
        if stage in {InterviewStage.COMPANY_QA, InterviewStage.CLOSING}:
            return "wrap_up"
        if stage == InterviewStage.PROJECT_DEEP_DIVE or dimension in {
            "performance_troubleshooting",
            "system_design",
            "scenario_design",
        }:
            return "scenario"
        if stage == InterviewStage.JD_MATCH or dimension in {
            "focus_experience",
            "experience_validation",
            "jd_match",
            "jd_match_case",
            "jd_readiness",
            "jd_gap_analysis",
            "project_deep_dive",
            "project_tradeoff",
            "internship_experience",
            "project_experience",
        }:
            return "experience"
        return "stack"

    @staticmethod
    def _technical_bucket_plan(question_count: int) -> dict[str, dict[str, int]]:
        total = max(1, int(question_count or 0))
        if total >= 12:
            scenario_target = 3
            stack_target = min(8, max(5, total - scenario_target - 5))
            experience_target = max(3, total - scenario_target - stack_target)
            return {
                "stack": {"min": 5, "target": stack_target, "max": 8},
                "scenario": {"min": 3, "target": scenario_target, "max": 3},
                "experience": {"min": 3, "target": min(5, experience_target), "max": 5},
            }
        if total >= 9:
            scenario_target = 3
            stack_target = max(4, total - scenario_target - 3)
            experience_target = max(2, total - scenario_target - stack_target)
            return {
                "stack": {"min": 4, "target": min(6, stack_target), "max": 7},
                "scenario": {"min": 3, "target": 3, "max": 3},
                "experience": {"min": 2, "target": min(4, experience_target), "max": 4},
            }
        scenario_target = min(2, max(1, total // 3))
        stack_target = max(1, total - scenario_target - 1)
        experience_target = max(1, total - scenario_target - stack_target)
        return {
            "stack": {"min": 1, "target": stack_target, "max": max(1, total - scenario_target)},
            "scenario": {"min": scenario_target, "target": scenario_target, "max": scenario_target},
            "experience": {"min": 1, "target": experience_target, "max": max(1, total - stack_target - scenario_target)},
        }

    def _build_stage_seed_questions(
        self,
        *,
        job_requirements: str,
        skills: list[str],
        language: str,
    ) -> list[dict]:
        primary_skill = next((str(item).strip() for item in (skills or []) if str(item).strip()), "核心技能")
        job_hint = (job_requirements or "").strip()[:80] or "岗位要求"
        if language == "en-US":
            primary_skill = primary_skill or "core skill"
            job_hint = (job_requirements or "").strip()[:80] or "job requirements"
            return [
                {"stage": InterviewStage.SELF_INTRO, "question": "Please give me a short self-introduction, focusing on your recent project and role.", "dimension": "self_intro", "expected_signal": "Recent experience, role, and main project", "followup_condition": "Follow up if the introduction is scattered", "max_followups": 1, "success_signals": ["recent experience", "role", "main project"]},
                {"stage": InterviewStage.PROJECT_DEEP_DIVE, "question": f"In the project where you used {primary_skill} most deeply, what was the hardest part you handled yourself?", "dimension": "project_deep_dive", "expected_signal": "Personal ownership, technical challenge, handling approach", "followup_condition": "Follow up if ownership is unclear", "max_followups": 2, "success_signals": ["personal ownership", "technical challenge", "handling approach"]},
                {"stage": InterviewStage.PROJECT_DEEP_DIVE, "question": "Which design choice in that project needed the most trade-off, and why?", "dimension": "project_tradeoff", "expected_signal": "Trade-off thinking, constraints, design rationale", "followup_condition": "Follow up if trade-offs are missing", "max_followups": 2, "success_signals": ["trade-off", "constraints", "design rationale"]},
                {"stage": InterviewStage.JD_MATCH, "question": "Looking at your collaboration or internship-like experience, what did you really own end to end?", "dimension": "experience_validation", "expected_signal": "Actual ownership, delivery depth, collaboration boundary", "followup_condition": "Follow up if the answer stays at team level", "max_followups": 2, "success_signals": ["actual ownership", "delivery depth", "collaboration boundary"]},
                {"stage": InterviewStage.GENERAL_PROBE, "question": "If one of your services suddenly slows down online, what troubleshooting order would you follow?", "dimension": "capability_probe", "expected_signal": "Troubleshooting path, metrics awareness, diagnosis order", "followup_condition": "Follow up if there are no concrete steps", "max_followups": 2, "success_signals": ["troubleshooting path", "metrics awareness", "diagnosis order"]},
                {"stage": InterviewStage.COMPANY_QA, "question": "After the technical part, what would you most want to know about this role or team?", "dimension": "company_qa", "expected_signal": "Candidate concern, role understanding focus", "followup_condition": "No follow-up unless unclear", "max_followups": 1, "success_signals": ["candidate concern", "role understanding focus"]},
            ]
        return [
            {"stage": InterviewStage.SELF_INTRO, "question": "先简单介绍一下你自己，重点说最近的项目和你的角色。", "dimension": "self_intro", "expected_signal": "最近经历、项目方向、角色定位", "followup_condition": "如果介绍发散，追问最近项目和核心职责", "max_followups": 1, "success_signals": ["最近经历", "项目方向", "角色定位"]},
            {"stage": InterviewStage.PROJECT_DEEP_DIVE, "question": f"你用 {primary_skill} 最深的那个项目里，最难的点是什么？你当时是怎么处理的？", "dimension": "project_deep_dive", "expected_signal": "个人职责、技术难点、处理方式", "followup_condition": "如果没有讲清本人做了什么，继续追问", "max_followups": 2, "success_signals": ["个人职责", "技术难点", "处理方式"]},
            {"stage": InterviewStage.PROJECT_DEEP_DIVE, "question": "那个项目里有没有哪个方案你们反复权衡过？最后为什么这么定？", "dimension": "project_tradeoff", "expected_signal": "取舍思路、约束条件、方案原因", "followup_condition": "如果没有说清取舍和约束，继续追问", "max_followups": 2, "success_signals": ["取舍思路", "约束条件", "方案原因"]},
            {"stage": InterviewStage.JD_MATCH, "question": "如果看实习或协作经历，你真正独立负责到交付的是哪一块？", "dimension": "experience_validation", "expected_signal": "真实负责范围、交付深度、协作边界", "followup_condition": "如果回答还停留在团队层面，继续追问", "max_followups": 2, "success_signals": ["真实负责范围", "交付深度", "协作边界"]},
            {"stage": InterviewStage.GENERAL_PROBE, "question": "如果你负责的服务线上突然变慢了，你一般按什么顺序排查？", "dimension": "capability_probe", "expected_signal": "排查路径、指标意识、定位顺序", "followup_condition": "如果没有具体排查步骤，继续追问", "max_followups": 2, "success_signals": ["排查路径", "指标意识", "定位顺序"]},
            {"stage": InterviewStage.COMPANY_QA, "question": f"技术部分聊完后，结合这个岗位“{job_hint}”，你最想了解我们哪一块？", "dimension": "company_qa", "expected_signal": "候选人关注点、岗位理解方向", "followup_condition": "除非候选人的问题不清楚，否则不继续追问", "max_followups": 1, "success_signals": ["候选人关注点", "岗位理解方向"]},
        ]

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
        """Blend rule + LLM questions with hard stage quotas."""
        keyword_tokens = self._extract_keyword_tokens(
            skills=skills,
            job_requirements=job_requirements,
            resume_text=resume_text,
            language=language,
        )
        candidates: list[dict] = []
        stage_seeds = self._build_stage_seed_questions(
            job_requirements=job_requirements,
            skills=skills,
            language=language,
        )
        for source, questions in (("rule", rule_questions), ("llm", llm_questions), ("seed", stage_seeds)):
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
        ranked.sort(
            key=lambda entry: (
                entry["score"],
                1 if entry["source"] == "llm" else 0,
                1 if entry["source"] == "seed" else 0,
            ),
            reverse=True,
        )

        bucket_plan = self._technical_bucket_plan(question_count)
        bucket_order = ("stack", "scenario", "experience")
        picked: list[dict] = []
        seen_questions: set[str] = set()
        seen_dimensions_by_bucket: dict[str, set[str]] = {}
        seen_skills_by_bucket: dict[str, set[str]] = {}
        bucket_counts = {bucket: 0 for bucket in bucket_order}

        def _bucket_items(bucket_name: str, *, seeds_only: bool | None = None) -> list[dict]:
            filtered: list[dict] = []
            for item in ranked:
                if self._question_bucket(item["question"]) != bucket_name:
                    continue
                if seeds_only is True and item["source"] != "seed":
                    continue
                if seeds_only is False and item["source"] == "seed":
                    continue
                filtered.append(item)
            return filtered

        def _try_pick(item: dict, bucket_name: str, *, enforce_diversity: bool) -> bool:
            question = item["question"]
            normalized_text = item["normalized_text"]
            if normalized_text in seen_questions:
                return False
            dimension = str(question.get("dimension") or "communication").strip().lower()
            target_skill = str(question.get("target_skill") or "").strip().lower()
            bucket_dims = seen_dimensions_by_bucket.setdefault(bucket_name, set())
            bucket_skills = seen_skills_by_bucket.setdefault(bucket_name, set())
            if enforce_diversity:
                if dimension and dimension in bucket_dims and item["source"] != "seed":
                    return False
                if target_skill and target_skill in bucket_skills and item["source"] != "seed":
                    return False
            picked.append(question)
            seen_questions.add(normalized_text)
            if dimension:
                bucket_dims.add(dimension)
            if target_skill:
                bucket_skills.add(target_skill)
            bucket_counts[bucket_name] = bucket_counts.get(bucket_name, 0) + 1
            return True

        for bucket_name in bucket_order:
            minimum = int(bucket_plan.get(bucket_name, {}).get("min", 0))
            for strict_mode in (True, False):
                if bucket_counts[bucket_name] >= minimum:
                    break
                for item in _bucket_items(bucket_name, seeds_only=False):
                    if _try_pick(item, bucket_name, enforce_diversity=strict_mode):
                        if bucket_counts[bucket_name] >= minimum or len(picked) >= question_count:
                            break
                if len(picked) >= question_count:
                    return picked[:question_count]
            if bucket_counts[bucket_name] >= minimum:
                continue
            for item in _bucket_items(bucket_name, seeds_only=True):
                if _try_pick(item, bucket_name, enforce_diversity=False):
                    if bucket_counts[bucket_name] >= minimum or len(picked) >= question_count:
                        break
            if len(picked) >= question_count:
                return picked[:question_count]

        for bucket_name in bucket_order:
            target = int(bucket_plan.get(bucket_name, {}).get("target", bucket_counts.get(bucket_name, 0)))
            maximum = int(bucket_plan.get(bucket_name, {}).get("max", target))
            limit = min(maximum, max(target, bucket_counts.get(bucket_name, 0)))
            for strict_mode in (True, False):
                if bucket_counts[bucket_name] >= limit:
                    break
                for item in _bucket_items(bucket_name, seeds_only=None):
                    if _try_pick(item, bucket_name, enforce_diversity=strict_mode):
                        if bucket_counts[bucket_name] >= limit or len(picked) >= question_count:
                            break
                if len(picked) >= question_count:
                    return picked[:question_count]

        ordered: list[dict] = []
        for bucket_name in bucket_order:
            for question in picked:
                if self._question_bucket(question) == bucket_name:
                    ordered.append(question)

        if len(ordered) >= question_count:
            return ordered[:question_count]

        for item in ranked:
            if len(ordered) >= question_count:
                break
            normalized_text = item["normalized_text"]
            if normalized_text in seen_questions:
                continue
            question = item["question"]
            bucket_name = self._question_bucket(question)
            maximum = int(bucket_plan.get(bucket_name, {}).get("max", question_count))
            if bucket_counts.get(bucket_name, 0) >= maximum and bucket_name in bucket_plan:
                continue
            if _try_pick(item, bucket_name, enforce_diversity=False):
                ordered.append(question)

        if len(ordered) >= question_count:
            return ordered[:question_count]

        for item in ranked:
            if len(ordered) >= question_count:
                break
            normalized_text = item["normalized_text"]
            if normalized_text in seen_questions:
                continue
            question = item["question"]
            if _try_pick(item, self._question_bucket(question), enforce_diversity=False):
                ordered.append(question)
        return ordered[:question_count]

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
        """鏋勫缓杩介棶 Prompt 涓婁笅鏂囥€?"""
        compact_answer = " ".join((transcript or "").strip().split())[:320]
        active_question = self._get_active_question_context(session_id=session_id) or {}
        current_question = str(active_question.get("question") or FOLLOWUP_DEFAULT_QUESTION).strip()
        expected_signal = str(active_question.get("expected_signal") or FOLLOWUP_DEFAULT_SIGNAL).strip()
        turns = self._session_repository.list_recent_turns(session_id, limit=20)
        summaries: list[str] = []
        for item in turns:
            text = " ".join((item.transcript or "").strip().split())
            if not text:
                continue
            speaker = FOLLOWUP_SPEAKER_CANDIDATE if item.speaker == SpeakerRole.CANDIDATE else FOLLOWUP_SPEAKER_AI
            summaries.append(f"{speaker}:{text[:240]}")
        # Handle next question preview for v4 natural transition
        next_q_text = ""
        try:
            # Look ahead for the next question to help the AI decide whether to transition
            q_pack = self._runtime_store.get_question_pack(session_id=session_id)
            if q_pack:
                state = self._runtime_store.get_session_state(session_id=session_id)
                current_idx = state.get("active_question_index", 0)
                if current_idx + 1 < len(q_pack):
                    next_q = q_pack[current_idx + 1]
                    next_q_text = f"\n澶囬€変笅涓€涓寮忛棶棰橈細{next_q.get('question')}\n"
        except Exception:
            pass

        return {
            "language": language,
            "stage": interview_stage,
            "current_question": current_question,
            "expected_signal": expected_signal,
            "answer": compact_answer,
            "last_turns_summary": " | ".join(summaries) if summaries else "鏃犲巻鍙蹭笂涓嬫枃",
            "confidence": f"{confidence:.2f}" if confidence is not None else "",
            "next_question_section": next_q_text,
            "stage_hint": "当前是 S2 暖场阶段，请保持简洁。如果候选人已提供基本背景，请尽快引导至技术深挖，避免重复确认职责。" if interview_stage == "S2" else "",
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
        """鏍规嵁鏁忔劅鍜岀疆淇″害绛栫暐鍐冲畾缁х画銆佹嫤鎴垨杞汉宸ャ€?"""
        runtime_mode = self._resolve_runtime_mode()
        if runtime_mode == RuntimeMode.RULE_ONLY:
            return InterviewAction.AUTO_CONTINUE, "rule_only_mode", []

        sensitive_keywords = ("身份证", "银行卡", "宗教", "种族", "违法")
        flags: list[str] = []
        for keyword in sensitive_keywords:
            if keyword in (transcript or ""):
                flags.append(build_sensitive_flag(keyword))

        if flags:
            self._session_repository.create_handoff(
                session_id=session_id,
                reason=BlockReason.SENSITIVE_CONTENT,
                trigger_flags=flags,
                operator="system",
                payload={"transcript": transcript[:200]},
            )
            self._session_repository.update_status(
                session_id,
                status=InterviewSessionStatus.FAILED,
                payload_patch={PayloadKey.BLOCKED_REASON: BlockReason.SENSITIVE_CONTENT, PayloadKey.BLOCKED_FLAGS: flags},
            )
            return InterviewAction.BLOCKED, BlockReason.SENSITIVE_CONTENT, flags

        min_confidence = 0.60
        max_low_streak = 2
        session_entity = self._session_repository.get(session_id)
        session_payload = dict(session_entity.payload or {})
        low_streak = int(session_payload.get(PayloadKey.LOW_CONFIDENCE_STREAK, 0))
        if confidence is not None and confidence < min_confidence:
            low_streak += 1
            flags.append(LOW_CONFIDENCE_FLAG)
            self._session_repository.update_status(
                session_id,
                status=session_entity.status,
                payload_patch={PayloadKey.LOW_CONFIDENCE_STREAK: low_streak},
            )
            if low_streak >= max_low_streak:
                self._session_repository.create_handoff(
                    session_id=session_id,
                    reason=HandoffReason.LOW_CONFIDENCE_STREAK,
                    trigger_flags=flags,
                    operator="system",
                    payload={"confidence": confidence, "streak": low_streak},
                )
                self._session_repository.update_status(
                    session_id,
                    status=InterviewSessionStatus.FAILED,
                    payload_patch={PayloadKey.HANDOFF_REASON: HandoffReason.LOW_CONFIDENCE_STREAK, PayloadKey.LOW_CONFIDENCE_STREAK: low_streak},
                )
                return InterviewAction.HANDOFF, HandoffReason.LOW_CONFIDENCE_STREAK, flags
            return InterviewAction.AUTO_CONTINUE, "low_confidence_but_within_threshold", flags

        if low_streak != 0:
            self._session_repository.update_status(
                session_id,
                status=session_entity.status,
                payload_patch={PayloadKey.LOW_CONFIDENCE_STREAK: 0},
            )
        return InterviewAction.AUTO_CONTINUE, "confidence_passed", flags

    def _advance_stage(self, session_id: str) -> str:
        """BE-011锛氭牴鎹€欓€変汉鍥炵瓟杞鎺ㄨ繘闈㈣瘯闃舵锛屾敮鎸侀噸鍏ャ€?"""
        turns = self._session_repository.list_turns(session_id)
        candidate_turn_count = len([item for item in turns if item.speaker == SpeakerRole.CANDIDATE])
        if candidate_turn_count <= 2:
            stage = InterviewStage.SELF_INTRO
        elif candidate_turn_count <= 5:
            stage = InterviewStage.TECH_STACK
        else:
            stage = InterviewStage.PROJECT_DEEP_DIVE
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
        """BE-012锛氱敓鎴愬彲瑙ｉ解釋杩介棶鍐呭锛屽紓甯稿垎鏀檷绾т负绌恒€?"""
        if action in {InterviewAction.HANDOFF, InterviewAction.BLOCKED}:
            return None
        if confidence is not None and confidence < 0.60:
            if language == "en-US":
                return "Please answer with one concrete case, including context, actions, and measurable result."
            return "请用一个具体案例补充你的回答，包含背景、行动与结果。"
        if len((transcript or "").strip()) < 18:
            if language == "en-US":
                return f"We are in {interview_stage or InterviewStageGroup.CORE} stage, please add more detail and measurable outcomes."
            return f"当前处于 {interview_stage or InterviewStageGroup.CORE} 阶段，请补充更多细节和量化结果。"
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
        """Build a stable fallback question pack."""

        normalized_skills = [str(item).strip() for item in (skills or []) if str(item).strip()]
        if not normalized_skills:
            normalized_skills = ["Java", "Spring Boot", "MySQL", "Redis"]

        middleware_keywords = ("mysql", "postgres", "redis", "kafka", "rocketmq", "rabbitmq", "es", "elasticsearch", "mongodb", "clickhouse")
        core_skills = normalized_skills[:2]
        while len(core_skills) < 2:
            core_skills.append("核心技术栈" if language != "en-US" else "core stack")

        middleware_skills = [
            skill for skill in normalized_skills
            if any(keyword in skill.lower() for keyword in middleware_keywords) and skill not in core_skills
        ][:2]
        for candidate in ["MySQL", "Redis"]:
            if len(middleware_skills) >= 2:
                break
            if candidate not in middleware_skills and candidate not in core_skills:
                middleware_skills.append(candidate)

        supplemental_skills = [
            skill for skill in normalized_skills
            if skill not in core_skills and skill not in middleware_skills
        ][:4]

        def _signals(*items: str) -> list[str]:
            return [item for item in items if item]

        def _q(*, question: str, dimension: str, expected_signal: str, followup_condition: str, stage: str = InterviewStage.TECH_STACK, bucket: str = "", max_followups: int = 2, success_signals: list[str] | None = None, target_skill: str = "", source_evidence: str = "") -> dict:
            return {
                "question": question,
                "dimension": dimension,
                "expected_signal": expected_signal,
                "followup_condition": followup_condition,
                "stage": stage,
                "bucket": bucket,
                "max_followups": max_followups,
                "success_signals": success_signals or [],
                "target_skill": target_skill,
                "source_evidence": source_evidence,
            }

        question_bank: list[dict] = []

        for skill in core_skills[:2]:
            if language == "en-US":
                question_bank.append(_q(question=f"You highlighted {skill} in your resume. In which project did you use it most deeply, and what exactly were you responsible for?", dimension="core_stack_validation", expected_signal="Project context, ownership, and depth of usage", followup_condition="Follow up if ownership or usage depth is unclear", bucket="stack", success_signals=_signals("project context", "ownership", "depth of usage"), target_skill=skill, source_evidence=f"resume_skill:{skill}"))
            else:
                question_bank.append(_q(question=f"你简历里重点写了 {skill}，它在哪个项目里用得最深？你当时具体负责了什么？", dimension="core_stack_validation", expected_signal="项目场景、个人职责、使用深度", followup_condition="如果没有讲清个人职责或真实使用深度，继续追问", bucket="stack", success_signals=_signals("项目场景", "个人职责", "使用深度"), target_skill=skill, source_evidence=f"resume_skill:{skill}"))

        for skill in middleware_skills[:2]:
            if language == "en-US":
                question_bank.append(_q(question=f"In your project, where did {skill} sit in the architecture, and why did you choose it there?", dimension="middleware_usage", expected_signal="Architecture position, selection reason, and practical usage", followup_condition="Follow up if the reason for using this component is vague", bucket="stack", success_signals=_signals("architecture position", "selection reason", "practical usage"), target_skill=skill, source_evidence=f"resume_skill:{skill}"))
            else:
                question_bank.append(_q(question=f"在你的真实项目里，{skill} 主要放在系统的哪个位置？你们为什么要在那一层用它？", dimension="middleware_usage", expected_signal="架构位置、选型原因、实际使用方式", followup_condition="如果没有说明为什么要用它，继续追问", bucket="stack", success_signals=_signals("架构位置", "选型原因", "实际使用方式"), target_skill=skill, source_evidence=f"resume_skill:{skill}"))

        for skill in supplemental_skills:
            if language == "en-US":
                question_bank.append(_q(question=f"For {skill}, what concrete problem did it help you solve in a real project, and how did you verify the effect afterward?", dimension="stack_verification", expected_signal="Real usage context, solved problem, and verification", followup_condition="Follow up if the answer lacks project evidence", bucket="stack", success_signals=_signals("real usage context", "solved problem", "verification"), target_skill=skill, source_evidence=f"resume_skill:{skill}"))
            else:
                question_bank.append(_q(question=f"回到你简历里的 {skill}，它在真实项目里主要帮你解决了什么问题？你后面是怎么验证效果的？", dimension="stack_verification", expected_signal="真实使用场景、解决的问题、验证方式", followup_condition="如果没有结合项目证据，继续追问", bucket="stack", success_signals=_signals("真实使用场景", "解决的问题", "验证方式"), target_skill=skill, source_evidence=f"resume_skill:{skill}"))

        if language == "en-US":
            question_bank.extend([
                _q(question="If the system latency suddenly rises after a release, what signals would you look at first, and how would you narrow it down?", dimension="performance_troubleshooting", expected_signal="Monitoring signals, diagnosis order, troubleshooting path", followup_condition="Follow up if there are no concrete troubleshooting steps", stage=InterviewStage.PROJECT_DEEP_DIVE, bucket="scenario", success_signals=_signals("monitoring signals", "diagnosis order", "troubleshooting path")),
                _q(question="Pick one design choice in your recent project that affected performance or stability. Why did you settle on that option?", dimension="system_design", expected_signal="Trade-off, constraints, design rationale", followup_condition="Follow up if the trade-off is unclear", stage=InterviewStage.PROJECT_DEEP_DIVE, bucket="scenario", success_signals=_signals("trade-off", "constraints", "design rationale")),
                _q(question="Suppose a core interface suddenly faces traffic several times higher than usual. How would you protect availability and avoid cascading failures?", dimension="scenario_design", expected_signal="Capacity protection, degradation strategy, stability thinking", followup_condition="Follow up if there are no concrete fallback measures", stage=InterviewStage.PROJECT_DEEP_DIVE, bucket="scenario", success_signals=_signals("capacity protection", "degradation strategy", "stability thinking")),
            ])
        else:
            question_bank.extend([
                _q(question="如果一次发布之后系统延迟突然升高了，你会先看哪些信号？再怎么一步步缩小排查范围？", dimension="performance_troubleshooting", expected_signal="监控信号、定位顺序、排查路径", followup_condition="如果没有具体排查步骤，继续追问", stage=InterviewStage.PROJECT_DEEP_DIVE, bucket="scenario", success_signals=_signals("监控信号", "定位顺序", "排查路径")),
                _q(question="结合你最近的项目，挑一个明显影响性能或稳定性的设计选择，说说你们为什么最后这么定。", dimension="system_design", expected_signal="取舍思路、系统约束、设计依据", followup_condition="如果没有说明取舍和约束，继续追问", stage=InterviewStage.PROJECT_DEEP_DIVE, bucket="scenario", success_signals=_signals("取舍思路", "系统约束", "设计依据")),
                _q(question="假设你负责的核心接口流量突然涨到平时的好几倍，你会怎么做才能先保住可用性，避免整个系统被拖垮？", dimension="scenario_design", expected_signal="容量保护、降级策略、稳定性思路", followup_condition="如果没有具体保护动作或兜底方案，继续追问", stage=InterviewStage.PROJECT_DEEP_DIVE, bucket="scenario", success_signals=_signals("容量保护", "降级策略", "稳定性思路")),
            ])

        job_hint = job_requirements[:120] if job_requirements else ("role requirements" if language == "en-US" else "岗位要求")
        if language == "en-US":
            question_bank.extend([
                _q(question=f"From the requirement '{job_hint}', which part matches your past experience most directly? Walk me through a concrete case.", dimension="jd_match_case", expected_signal="JD mapping, concrete case, evidence", followup_condition="Follow up if the answer is broad but not evidence-based", stage=InterviewStage.JD_MATCH, bucket="experience", success_signals=_signals("JD mapping", "concrete case", "evidence"), source_evidence=f"jd:{job_hint}"),
                _q(question="Which requirement in this role would you be most ready to pick up immediately, and what experience gives you that confidence?", dimension="jd_readiness", expected_signal="Readiness judgment, delivery experience", followup_condition="Follow up if confidence is not backed by actual work", stage=InterviewStage.JD_MATCH, bucket="experience", success_signals=_signals("readiness judgment", "delivery experience"), source_evidence=f"jd:{job_hint}"),
                _q(question="Which requirement in this JD is less familiar to you, and how would you close that gap after joining?", dimension="jd_gap_analysis", expected_signal="Gap awareness, learning plan, realistic assessment", followup_condition="Follow up if there is no concrete plan", stage=InterviewStage.JD_MATCH, bucket="experience", success_signals=_signals("gap awareness", "learning plan", "realistic assessment"), source_evidence=f"jd:{job_hint}"),
                _q(question="Looking back at your internship or project work, which part best reflects your real ownership from design to delivery?", dimension="experience_validation", expected_signal="Ownership boundary, delivery depth, concrete responsibility", followup_condition="Follow up if the answer stays at team level", stage=InterviewStage.JD_MATCH, bucket="experience", success_signals=_signals("ownership boundary", "delivery depth", "concrete responsibility")),
            ])
        else:
            question_bank.extend([
                _q(question=f"结合这个岗位要求“{job_hint}”，你过去哪段经历和它最直接匹配？请讲一个具体例子。", dimension="jd_match_case", expected_signal="JD 对应关系、具体案例、真实证据", followup_condition="如果只有泛泛匹配没有案例，继续追问", stage=InterviewStage.JD_MATCH, bucket="experience", success_signals=_signals("JD 对应关系", "具体案例", "真实证据"), source_evidence=f"jd:{job_hint}"),
                _q(question="这个岗位里你觉得自己上手最快、最有把握的是哪一块？你的信心来自哪段真实经历？", dimension="jd_readiness", expected_signal="就绪度判断、交付经历", followup_condition="如果信心没有建立在真实经历上，继续追问", stage=InterviewStage.JD_MATCH, bucket="experience", success_signals=_signals("就绪度判断", "交付经历"), source_evidence=f"jd:{job_hint}"),
                _q(question="如果看这份 JD，有哪一块是你相对不熟的？如果入职后要补上，你会怎么补？", dimension="jd_gap_analysis", expected_signal="差距认知、补足计划、现实评估", followup_condition="如果没有具体补足计划，继续追问", stage=InterviewStage.JD_MATCH, bucket="experience", success_signals=_signals("差距认知", "补足计划", "现实评估"), source_evidence=f"jd:{job_hint}"),
                _q(question="回头看你的实习或项目经历，哪一部分最能体现你是从设计到交付真正负责过的？", dimension="experience_validation", expected_signal="职责边界、交付深度、真实负责内容", followup_condition="如果回答还停留在团队层面，继续追问", stage=InterviewStage.JD_MATCH, bucket="experience", success_signals=_signals("职责边界", "交付深度", "真实负责内容")),
            ])

        return question_bank[:question_count]

    def _build_run_id(self, *, session_id: str, runtime_mode: str, turns) -> str:
        """根据会话数据生成一个稳定的 run_id，用于报告幂等和版本追溯。"""
        import hashlib
        import json
        data = {
            "session_id": session_id,
            "runtime_mode": runtime_mode,
            "turn_count": len(turns),
            "last_turn_at": str(turns[-1].created_at) if turns else "empty",
        }
        return hashlib.md5(json.dumps(data, sort_keys=True).encode()).hexdigest()

    def _build_followup_question_with_llm(
        self,
        *,
        session_id: str,
        seq: int | None = None,
        transcript: str,
        confidence: float,
        interview_stage: str,
        language: str = "zh-CN",
        write_observability: bool = False,
        prefetch_mode: bool = False,
        abort_event: threading.Event | None = None,
        emit_delta: bool = True,
        print_stream: bool = False,
    ) -> Generator[str, None, None]:
        """Use LLM to generate a deep-dive follow-up question based on candidate response."""
        prompt_ctx = self._build_followup_prompt_context(
            session_id=session_id,
            transcript=transcript,
            confidence=confidence,
            interview_stage=interview_stage,
            language=language,
        )
        template = self._resolve_prompt_template(
            task_key=PromptTaskKey.INTERVIEW_FOLLOWUP,
            default_version="v3"
        )
        try:
            rendered = template.render(**prompt_ctx)
        except KeyError:
            logger.warning("Invalid runtime prompt placeholders for task=interview_followup, fallback to bundled v3")
            template = get_prompt_template(PromptTaskKey.INTERVIEW_FOLLOWUP, "v3")
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
        llm_first_token_state = {"recorded": False}

        def _on_text_delta(delta: str) -> None:
            if not delta or llm_first_token_state["recorded"] or seq is None:
                return
            _record_duplex_timeline_marker(
                session_id=session_id,
                seq=seq,
                marker_key="llm_first_token_at_ms",
            )
            llm_first_token_state["recorded"] = True

        text_stream = llm_client.stream_invoke(
            InvokeContext(
                task_key=PromptTaskKey.INTERVIEW_FOLLOWUP,
                trace_id=f"ai-intv-fu-stream-{session_id}-{uuid.uuid4().hex[:8]}",
                prompt=prompt,
                entity_type="ai_interview_session",
                entity_id=session_id,
            ),
            on_text_delta=_on_text_delta,
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
                    event_type=InterviewEventType.LLM_SENTENCE,
                    payload={"text": sentence, "is_final": False}
                )
            if print_stream:
                print(f"Speculative LLM Sentence: {sentence}", flush=True)
            yield sentence

    # 标记该方法为流式，以便编排器识别
    _build_followup_question_with_llm.is_streaming = True


def _get_singleton_asr_provider() -> "ASRProvider":
    """杩斿洖杩涚▼绾?ASR Provider 鍗曚緥锛堝弻妫€閿侊級銆?"""
    global _ASR_PROVIDER_SINGLETON
    if _ASR_PROVIDER_SINGLETON is None:
        with _PROVIDER_SINGLETON_LOCK:
            if _ASR_PROVIDER_SINGLETON is None:
                _ASR_PROVIDER_SINGLETON = create_asr_provider(get_settings())
                logger.info("[Provider] ASR provider singleton created: %s", type(_ASR_PROVIDER_SINGLETON).__name__)
    return _ASR_PROVIDER_SINGLETON


def _get_singleton_tts_provider() -> "TTSProvider":
    """杩斿洖杩涚▼绾?TTS Provider 鍗曚緥锛堝弻妫€閿侊級銆?"""
    global _TTS_PROVIDER_SINGLETON
    if _TTS_PROVIDER_SINGLETON is None:
        with _PROVIDER_SINGLETON_LOCK:
            if _TTS_PROVIDER_SINGLETON is None:
                _TTS_PROVIDER_SINGLETON = create_tts_provider(get_settings())
                logger.info("[Provider] TTS provider singleton created: %s", type(_TTS_PROVIDER_SINGLETON).__name__)
    return _TTS_PROVIDER_SINGLETON


def get_ai_interview_service(session: Session) -> AIInterviewService:
    """杩斿洖缁戝畾褰撳墠 DB 浼氳瘽鐨?AI 闈㈣瘯鏈嶅姟瀹炰緥銆?

    ASR/TTS provider 涓鸿繘绋嬬骇鍗曚緥锛屼笉闅?DB session 閲嶅缓锛?
    閬垮厤 NLS 绛夋湁鐘舵€?provider 姣忔璇锋眰閮介噸鏂版彙鎵嬨€?
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
        invitation_repository=AIInterviewInvitationRepository(session),
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
