"""Cleaned docstring."""

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

# NOTE: cleaned mojibake comment.
# NOTE: cleaned mojibake comment.
# NOTE: cleaned mojibake comment.
# NOTE: cleaned mojibake comment.
_PROVIDER_SINGLETON_LOCK = threading.Lock()
_ASR_PROVIDER_SINGLETON: "ASRProvider | None" = None
_TTS_PROVIDER_SINGLETON: "TTSProvider | None" = None

# Turn-level deduplication markers for duplex flow
_DUPLEX_FINALIZE_LOCK = threading.Lock()
_DUPLEX_FINALIZED_SEQ: dict[str, set[int]] = {}
_DUPLEX_TIMELINE_LOCK = threading.Lock()
_DUPLEX_TIMELINE_MARKERS: dict[str, dict[int, dict[str, int]]] = {}
from sqlalchemy.orm import Session
from ...content.ai_interviews import (
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
from ...core.config import get_settings
from ...core.exceptions import InvalidStateError
from ...db.session import SessionLocal
from ...domain.constants import (
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
from ...repositories.ai_interviews import (
    AIInterviewInvitationRepository,
    AIInterviewSessionRepository,
)
from ...repositories.ai_observability import AIObservabilityRepository
from ...repositories.ai_runtime import AIRuntimeRepository
from ...repositories.candidates import CandidateRepository
from ...repositories.events import EventRepository
from ...repositories.interviews import InterviewRepository
from ...repositories.jobs import JobRepository
from ...schemas.ai_interviews import (
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
from ..interview_runtime.question_flow import InterviewQuestionFlowEngine
from ..interview_runtime.question_schema import normalize_question_item, normalize_question_pack
from ..interview_runtime.question_seed_builder import build_stage_seed_questions
from ..interview_runtime.runtime_engine import InterviewRuntimeEngine
from ..interview_runtime.store import InterviewRuntimeStore
from ..interview_runtime import get_interview_runtime_store
from ..llm.client import InvokeContext, LLMClient
from ..llm.guardrails import GuardrailService
from ..llm.prompts import PromptTemplate, get_prompt_template
from ..llm.router import ModelRouter
from ..orchestrator.event_bus import DEFAULT_INTERVIEW_EVENT_BUS
from ..orchestrator.realtime import RealtimeOrchestrator
from ..rtc.base import RTCGateway
from ..rtc.factory import create_rtc_gateway
from ..speech.base import ASRProvider, TTSProvider
from ..speech.factory import create_asr_provider, create_tts_provider
from ..ten_runtime import TENRuntimeManager
from ..enterprise_assessment import EnterpriseAssessmentService, get_enterprise_assessment_service

# NOTE: cleaned mojibake comment.

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


