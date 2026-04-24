from __future__ import annotations

from ai_hr.services.orchestrator.realtime import RealtimeOrchestrator
from ai_hr.services.speech.base import ASRProvider, ASRStreamResult, TTSProvider, TTSStreamResult


class _ASROk(ASRProvider):
    provider_name = "mock"

    def transcribe_stream(
        self,
        *,
        session_id: str,
        seq: int,
        text_hint: str,
        audio_base64: str | None,
        confidence: float,
        latency_ms: int,
    ) -> ASRStreamResult:
        return ASRStreamResult(transcript=text_hint or "ok", confidence=confidence, latency_ms=latency_ms, provider=self.provider_name)


class _TTSOk(TTSProvider):
    provider_name = "mock"

    def synthesize_stream(self, *, session_id: str, text: str, voice: str, chunk_size: int) -> TTSStreamResult:
        return TTSStreamResult(chunks=[text], audio_uris=[f"mock://tts/{session_id}/1.wav"], provider=self.provider_name)


class _TTSFail(TTSProvider):
    provider_name = "mock"

    def synthesize_stream(self, *, session_id: str, text: str, voice: str, chunk_size: int) -> TTSStreamResult:
        raise RuntimeError("tts down")


def test_orchestrator_should_fallback_to_rule_when_llm_fails() -> None:
    orchestrator = RealtimeOrchestrator(asr_provider=_ASROk(), tts_provider=_TTSOk())
    result = orchestrator.process_candidate_turn(
        session_id="s1",
        seq=1,
        transcript_hint="候选人回答",
        audio_base64=None,
        confidence=0.8,
        language="zh-CN",
        runtime_mode="llm_assist",
        llm_enabled=True,
        decide_action=lambda transcript, confidence: ("auto_continue", "ok", []),
        build_rule_followup=lambda transcript, confidence, stage, language, action: "规则追问",
        build_llm_followup=lambda transcript, confidence, stage, language: (_ for _ in ()).throw(RuntimeError("llm down")),
        interview_stage="core",
    )
    assert result.followup_question == "规则追问"
    assert result.degradation_mode == "llm_to_rule"


def test_orchestrator_should_fallback_to_text_when_tts_fails() -> None:
    orchestrator = RealtimeOrchestrator(asr_provider=_ASROk(), tts_provider=_TTSFail())
    result = orchestrator.process_candidate_turn(
        session_id="s1",
        seq=1,
        transcript_hint="candidate answer",
        audio_base64=None,
        confidence=0.8,
        language="en-US",
        runtime_mode="rule_only",
        llm_enabled=False,
        decide_action=lambda transcript, confidence: ("auto_continue", "ok", []),
        build_rule_followup=lambda transcript, confidence, stage, language, action: "rule followup",
        build_llm_followup=lambda transcript, confidence, stage, language: "llm followup",
        interview_stage="core",
    )
    assert result.followup_question == "rule followup"
    assert result.followup_audio_uris == []
    assert result.degradation_mode == "tts_to_text_only"
