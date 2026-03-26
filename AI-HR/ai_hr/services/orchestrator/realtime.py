"""Realtime orchestration: ASR -> policy -> follow-up -> TTS."""

from __future__ import annotations

import concurrent.futures
import time
import logging
from dataclasses import dataclass
from typing import Callable

from ...core.config import get_settings
from ..speech.base import ASRProvider, TTSProvider
from .followup_cache import DEFAULT_FOLLOWUP_CACHE
from .streaming_utils import split_sentences

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OrchestratorResult:
    transcript: str
    action: str | None
    decision_reason: str | None
    policy_flags: list[str]
    followup_question: str | None
    followup_audio_uris: list[str]
    degradation_mode: str | None
    latency_breakdown: dict[str, int]


class RealtimeOrchestrator:
    """Realtime orchestration with low-latency optimizations and degradations."""

    def __init__(self, *, asr_provider: ASRProvider, tts_provider: TTSProvider):
        self._asr_provider = asr_provider
        self._tts_provider = tts_provider
        self._settings = get_settings()

    def process_candidate_turn(
        self,
        *,
        session_id: str,
        seq: int,
        transcript_hint: str,
        audio_base64: str | None,
        confidence: float | None,
        language: str,
        runtime_mode: str,
        llm_enabled: bool,
        decide_action: Callable[[str, float | None], tuple[str, str, list[str]]],
        build_rule_followup: Callable[[str, float | None, str, str, str | None], str | None],
        build_llm_followup: Callable[[str, float | None, str, str], str | None],
        interview_stage: str,
        question_id: str | None = None,
        followup_question: str | None = None,
        tts_voice: str = "default",
        tts_enabled: bool = True,
        on_audio_packet: Callable[[dict], None] | None = None,
    ) -> OrchestratorResult:
        """串行处理候选人回合。如果提供了 on_audio_packet，则会尝试流式合成响应。"""
        # Note: To avoid duplicating the entire logic, we can keep the serial version
        # but integrate streaming inside it.
        degradation_mode: str | None = None
        followup_audio_uris: list[str] = []
        streamed_in_llm_block = False
        policy_flags: list[str] = []

        asr_start = time.perf_counter()
        if not audio_base64:
            transcript = transcript_hint
            asr_latency_ms = 0
        else:
            asr_result = self._asr_provider.transcribe_stream(
                session_id=session_id,
                seq=seq,
                text_hint=transcript_hint,
                audio_base64=audio_base64,
                confidence=confidence if confidence is not None else 0.9,
                latency_ms=500,
            )
            asr_latency_ms = int((time.perf_counter() - asr_start) * 1000)
            transcript = asr_result.transcript

        decision_start = time.perf_counter()
        action, decision_reason, decision_flags = decide_action(transcript, confidence)
        decision_latency_ms = int((time.perf_counter() - decision_start) * 1000)
        policy_flags.extend(decision_flags)

        llm_latency_ms = 0
        followup_question: str | None = None
        cache_hit = False
        warmup_future: concurrent.futures.Future | None = None
        warmup_executor: concurrent.futures.ThreadPoolExecutor | None = None

        if action not in {"handoff", "blocked"}:
            warmup_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            warmup_future = warmup_executor.submit(self._tts_provider.warmup, session_id=session_id, voice=tts_voice)

            cache_key = DEFAULT_FOLLOWUP_CACHE.build_key(
                stage=interview_stage,
                language=language,
                transcript=transcript,
                question_id=question_id,
                session_id=session_id,
            )
            cache_entry = DEFAULT_FOLLOWUP_CACHE.get(cache_key)
            if cache_entry is not None:
                cache_hit = True
                followup_question = cache_entry.question

            llm_start = time.perf_counter()
            if not followup_question and llm_enabled:
                try:
                    if on_audio_packet and hasattr(build_llm_followup, "is_streaming") and build_llm_followup.is_streaming:
                        # 流式路径：出一句合一句
                        text_stream = build_llm_followup(transcript, confidence, interview_stage, language)
                        if text_stream:
                            full_text_list = []
                            def _delta_logger(stream):
                                for chunk in stream:
                                    if chunk:
                                        print(f"DEBUG [LLM Delta] Session: {session_id}, Chunk: '{chunk}'")
                                    yield chunk
                            
                            for sentence in split_sentences(_delta_logger(text_stream)):
                                full_text_list.append(sentence)
                                print(f"DEBUG [LLM Stream] Session: {session_id}, Sentence: {sentence}")
                                # 立即触发该句的 TTS 合成
                                try:
                                    for packet in self._tts_provider.synthesize_stream_iter(
                                        session_id=session_id,
                                        text=sentence,
                                        voice=tts_voice,
                                        chunk_size=24
                                    ):
                                        if packet.get("audio_uri"):
                                            print(f"DEBUG [TTS Stream] Session: {session_id}, Packet: {packet.get('index')}, URL: {packet.get('audio_uri')[:60]}...")
                                        on_audio_packet(packet)
                                except Exception as tts_err:
                                    logger.warning(f"Streaming TTS error for sentence '{sentence}': {tts_err}")
                            followup_question = "".join(full_text_list)
                            streamed_in_llm_block = True
                    else:
                        res = build_llm_followup(transcript, confidence, interview_stage, language)
                        # Robust check for generators/iterators to avoid JSON serialization errors
                        if res is not None and not isinstance(res, str) and hasattr(res, "__iter__"):
                            followup_question = "".join(list(res))
                        else:
                            followup_question = res
                    
                    if followup_question:
                        DEFAULT_FOLLOWUP_CACHE.set(cache_key, question=followup_question, reason="llm")
                except Exception as llm_err:
                    logger.error(f"LLM followup error: {llm_err}", exc_info=True)
                    followup_question = None
                    degradation_mode = "llm_to_rule"
            llm_latency_ms = int((time.perf_counter() - llm_start) * 1000)

            if not followup_question:
                followup_question = build_rule_followup(transcript, confidence, interview_stage, language, action)
                if followup_question:
                    DEFAULT_FOLLOWUP_CACHE.set(cache_key, question=followup_question, reason="rule")

        tts_start = time.perf_counter()
        if followup_question and tts_enabled:
            if warmup_future is not None:
                try:
                    warmup_future.result(timeout=0.25)
                except Exception:
                    pass
            try:
                if not streamed_in_llm_block:
                    if on_audio_packet:
                        # 对于由于缓存命中或预取跳过 LLM 流的场景，此处进行补播
                        print(f"DEBUG [TTS Replay] Session: {session_id}, Playing existing followup: {followup_question[:100]}...")
                        from .streaming_utils import split_sentences
                        for sentence in split_sentences([followup_question]):
                            for packet in self._tts_provider.synthesize_stream_iter(
                                session_id=session_id,
                                text=sentence,
                                voice=tts_voice,
                                chunk_size=24,
                            ):
                                on_audio_packet(packet)
                                if packet.get("audio_uri"):
                                    followup_audio_uris.append(packet["audio_uri"])
                    else:
                        # 兼容非流式路径
                        tts_result = self._tts_provider.synthesize_stream(
                            session_id=session_id,
                            text=followup_question,
                            voice=tts_voice,
                            chunk_size=24,
                        )
                        followup_audio_uris = list(tts_result.audio_uris)
            except Exception:
                followup_audio_uris = []
                degradation_mode = "tts_to_text_only" if degradation_mode is None else f"{degradation_mode}+tts_to_text_only"
        tts_latency_ms = int((time.perf_counter() - tts_start) * 1000)

        if warmup_executor is not None:
            warmup_executor.shutdown(wait=True, cancel_futures=True)

        # 回合结束，清理 ASR 累积状态，防止下一轮回合串音
        try:
            self._asr_provider.flush(session_id=session_id)
        except Exception:
            pass

        e2e_latency_ms = asr_latency_ms + decision_latency_ms + llm_latency_ms + tts_latency_ms
        return OrchestratorResult(
            transcript=transcript,
            action=action,
            decision_reason=decision_reason,
            policy_flags=policy_flags,
            followup_question=followup_question,
            followup_audio_uris=followup_audio_uris,
            degradation_mode=degradation_mode,
            latency_breakdown={
                "asr_ms": asr_latency_ms,
                "decision_ms": decision_latency_ms,
                "llm_ms": llm_latency_ms,
                "tts_ms": tts_latency_ms,
                "e2e_ms": e2e_latency_ms,
                "llm_cache_hit": 1 if cache_hit else 0,
            },
        )
