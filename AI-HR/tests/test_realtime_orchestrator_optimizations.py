from __future__ import annotations

from ai_hr.services.orchestrator.followup_cache import FollowupCache
from ai_hr.services.orchestrator.realtime import RealtimeOrchestrator
from ai_hr.services.speech.base import ASRStreamResult, TTSStreamResult


class _MockASR:
    def transcribe_stream(self, **kwargs):  # noqa: ANN003
        return ASRStreamResult(transcript="我优化了查询性能", confidence=0.9, latency_ms=100, provider="mock")


class _MockTTS:
    def __init__(self):
        self.warmup_called = 0
        self.synthesize_called = 0

    def warmup(self, *, session_id: str, voice: str) -> None:
        self.warmup_called += 1

    def synthesize_stream(self, **kwargs):  # noqa: ANN003
        self.synthesize_called += 1
        return TTSStreamResult(chunks=["追问"], audio_uris=["data:audio/mpeg;base64,AA=="], provider="mock")


def test_realtime_orchestrator_should_use_cache_and_warmup() -> None:
    tts = _MockTTS()
    orchestrator = RealtimeOrchestrator(asr_provider=_MockASR(), tts_provider=tts)

    llm_called = {"count": 0}

    def _decide_action(transcript: str, confidence: float | None):  # noqa: ANN001
        return "auto_continue", "ok", []

    def _rule_followup(transcript: str, confidence: float | None, stage: str, language: str, action: str | None):  # noqa: ANN001
        return "请补充量化指标"

    def _llm_followup(transcript: str, confidence: float | None, stage: str, language: str):  # noqa: ANN001
        llm_called["count"] += 1
        return "请补充量化指标"

    first = orchestrator.process_candidate_turn(
        session_id="s1",
        seq=1,
        transcript_hint="",
        audio_base64="UklGRg==",
        confidence=0.9,
        language="zh-CN",
        runtime_mode="llm_assist",
        llm_enabled=True,
        decide_action=_decide_action,
        build_rule_followup=_rule_followup,
        build_llm_followup=_llm_followup,
        interview_stage="core",
    )
    assert first.followup_question == "请补充量化指标"

    second = orchestrator.process_candidate_turn(
        session_id="s1",
        seq=2,
        transcript_hint="",
        audio_base64="UklGRg==",
        confidence=0.9,
        language="zh-CN",
        runtime_mode="llm_assist",
        llm_enabled=True,
        decide_action=_decide_action,
        build_rule_followup=_rule_followup,
        build_llm_followup=_llm_followup,
        interview_stage="core",
    )
    assert second.followup_question == "请补充量化指标"
    assert llm_called["count"] == 1
    assert tts.warmup_called >= 2
    assert tts.synthesize_called >= 2

def test_followup_cache_key_should_include_question_id() -> None:
    cache = FollowupCache(ttl_seconds=60)
    key_a = cache.build_key(stage="core_questions", language="zh-CN", transcript="same transcript", question_id="q1")
    key_b = cache.build_key(stage="core_questions", language="zh-CN", transcript="same transcript", question_id="q2")
    assert key_a != key_b
