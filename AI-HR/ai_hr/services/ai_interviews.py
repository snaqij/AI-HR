"""AI interview service facade composed from split modules."""

from __future__ import annotations

from .ai_interviews_parts.ai_interviews_shared import *
from .ai_interviews_parts.ai_interviews_shared import (
    _ASR_PROVIDER_SINGLETON,
    _PROVIDER_SINGLETON_LOCK,
    _TTS_PROVIDER_SINGLETON,
)
from .ai_interviews_parts.ai_interviews_audio_duplex import AIInterviewAudioDuplexMixin
from .ai_interviews_parts.ai_interviews_audio_stream import AIInterviewAudioStreamMixin
from .ai_interviews_parts.ai_interviews_question_bank import AIInterviewQuestionBankMixin
from .ai_interviews_parts.ai_interviews_question_generation import AIInterviewQuestionGenerationMixin
from .ai_interviews_parts.ai_interviews_report_followup import AIInterviewReportFollowupMixin
from .ai_interviews_parts.ai_interviews_session_lifecycle import AIInterviewSessionLifecycleMixin
from .ai_interviews_parts.ai_interviews_session_rtc_ops import AIInterviewSessionRTCOpsMixin
from .ai_interviews_parts.ai_interviews_session_runtime_payload import AIInterviewSessionRuntimePayloadMixin


class AIInterviewService(
    AIInterviewSessionLifecycleMixin,
    AIInterviewSessionRTCOpsMixin,
    AIInterviewSessionRuntimePayloadMixin,
    AIInterviewQuestionGenerationMixin,
    AIInterviewQuestionBankMixin,
    AIInterviewReportFollowupMixin,
    AIInterviewAudioStreamMixin,
    AIInterviewAudioDuplexMixin,
):
    """Backward-compatible AI interview service."""


def _get_singleton_asr_provider() -> "ASRProvider":
    """Return process-level ASR provider singleton."""
    global _ASR_PROVIDER_SINGLETON
    if _ASR_PROVIDER_SINGLETON is None:
        with _PROVIDER_SINGLETON_LOCK:
            if _ASR_PROVIDER_SINGLETON is None:
                _ASR_PROVIDER_SINGLETON = create_asr_provider(get_settings())
                logger.info("[Provider] ASR provider singleton created: %s", type(_ASR_PROVIDER_SINGLETON).__name__)
    return _ASR_PROVIDER_SINGLETON


def _get_singleton_tts_provider() -> "TTSProvider":
    """Return process-level TTS provider singleton."""
    global _TTS_PROVIDER_SINGLETON
    if _TTS_PROVIDER_SINGLETON is None:
        with _PROVIDER_SINGLETON_LOCK:
            if _TTS_PROVIDER_SINGLETON is None:
                _TTS_PROVIDER_SINGLETON = create_tts_provider(get_settings())
                logger.info("[Provider] TTS provider singleton created: %s", type(_TTS_PROVIDER_SINGLETON).__name__)
    return _TTS_PROVIDER_SINGLETON


def get_ai_interview_service(session: Session) -> AIInterviewService:
    """Return AIInterviewService bound to current DB session.

    ASR/TTS providers are process-level singletons and should be reused across
    request-level DB sessions to avoid repeated handshake overhead.
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
    orchestrator = RealtimeOrchestrator(asr_provider=asr_provider, tts_provider=tts_provider)
    return AIInterviewService(
        session_repository=AIInterviewSessionRepository(session),
        invitation_repository=AIInterviewInvitationRepository(session),
        runtime_repository=runtime_repository,
        event_repository=EventRepository(session),
        llm_client=llm_client,
        asr_provider=asr_provider,
        tts_provider=tts_provider,
        interview_repository=InterviewRepository(session),
        candidate_repository=CandidateRepository(session),
        job_repository=JobRepository(session),
        ten_runtime_manager=TENRuntimeManager(settings),
        orchestrator=orchestrator,
        runtime_store=get_interview_runtime_store(),
        rtc_gateway=create_rtc_gateway(settings),
    )
