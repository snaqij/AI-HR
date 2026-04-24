"""Realtime orchestration: ASR -> policy -> follow-up -> TTS."""

from __future__ import annotations

import concurrent.futures
import time
import logging
import threading
import queue
from dataclasses import dataclass
from typing import Any, Callable
from ...core.config import get_settings
from ..speech.base import ASRProvider, TTSProvider
from .followup_cache import DEFAULT_FOLLOWUP_CACHE
from .streaming_utils import split_sentences
import struct

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


@dataclass(frozen=True, slots=True)
class _NormalizedTurnInput:
    transcript: str
    asr_latency_ms: int


@dataclass(frozen=True, slots=True)
class _FollowupDecision:
    action: str
    decision_reason: str
    decision_latency_ms: int
    policy_flags: list[str]
    followup_question: str | None
    followup_audio_uris: list[str]
    cache_hit: bool
    llm_latency_ms: int
    degradation_mode: str | None
    streamed_in_llm_block: bool
    warmup_future: concurrent.futures.Future | None
    warmup_executor: concurrent.futures.ThreadPoolExecutor | None


@dataclass(frozen=True, slots=True)
class _TtsOutcome:
    followup_audio_uris: list[str]
    tts_latency_ms: int
    degradation_mode: str | None


class RealtimeOrchestrator:
    """Realtime orchestration with low-latency optimizations and degradations."""

    def __init__(self, *, asr_provider: ASRProvider, tts_provider: TTSProvider):
        self._asr_provider = asr_provider
        self._tts_provider = tts_provider
        self._settings = get_settings()

    def _trim_pcm_silence(self, audio: bytes, threshold: int = 120) -> bytes:
        """去除 PCM (16bit, mono) 音频首尾的静音/数字化噪声（低振幅）片段。"""
        if not audio or len(audio) < 2:
            return audio
        try:
            # 16-bit PCM: 2 bytes per sample
            n_samples = len(audio) // 2
            samples = struct.unpack(f"{n_samples}h", audio)
            
            # Find first non-silent sample
            start_idx = 0
            for i, s in enumerate(samples):
                if abs(s) > threshold:
                    start_idx = i
                    break
            
            # Find last non-silent sample
            end_idx = n_samples
            for i in range(n_samples - 1, -1, -1):
                if abs(samples[i]) > threshold:
                    end_idx = i + 1
                    break
            
            if start_idx >= end_idx:
                return b""
            return struct.pack(f"{end_idx - start_idx}h", *samples[start_idx:end_idx])
        except Exception:
            return audio

    @staticmethod
    def _merge_degradation_mode(current: str | None, addition: str) -> str:
        if current is None:
            return addition
        return f"{current}+{addition}"

    def _normalize_turn_input(
        self,
        *,
        session_id: str,
        seq: int,
        transcript_hint: str,
        audio_base64: str | None,
        confidence: float | None,
    ) -> _NormalizedTurnInput:
        asr_start = time.perf_counter()
        if not audio_base64:
            return _NormalizedTurnInput(transcript=transcript_hint, asr_latency_ms=0)
        asr_result = self._asr_provider.transcribe_stream(
            session_id=session_id,
            seq=seq,
            text_hint=transcript_hint,
            audio_base64=audio_base64,
            confidence=confidence if confidence is not None else 0.9,
            latency_ms=500,
        )
        asr_latency_ms = int((time.perf_counter() - asr_start) * 1000)
        return _NormalizedTurnInput(transcript=asr_result.transcript, asr_latency_ms=asr_latency_ms)

    def _stream_llm_followup_with_tts(
        self,
        *,
        session_id: str,
        text_stream: str,
        tts_voice: str,
        on_audio_packet: Callable[[dict], None],
        abort_event: threading.Event | None,
    ) -> tuple[str, list[str], bool]:
        sentence_queue: queue.Queue[str] = queue.Queue(maxsize=16)
        job_queue: queue.Queue[queue.Queue[Any]] = queue.Queue(maxsize=16)
        full_text_list: list[str] = []
        followup_audio_uris: list[str] = []
        finished_fetching = threading.Event()
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

        def _fetch_sentences() -> None:
            try:
                for sentence in split_sentences(text_stream):
                    if abort_event and abort_event.is_set():
                        break
                    sentence_queue.put(sentence)
            except Exception as exc:
                logger.error("Error fetching sentences from LLM: %s", exc)
            finally:
                finished_fetching.set()

        def _synthesize_job(sentence: str, res_q: queue.Queue[Any]) -> None:
            try:
                for packet in self._tts_provider.synthesize_stream_iter(
                    session_id=session_id,
                    text=sentence,
                    voice=tts_voice,
                    chunk_size=24,
                ):
                    if abort_event and abort_event.is_set():
                        break
                    res_q.put(packet)
            except Exception as exc:
                logger.error("TTS Synthesis error for sentence '%s': %s", sentence[:20], exc)
            finally:
                res_q.put(None)

        def _coordinating_synthesis() -> None:
            try:
                while not (finished_fetching.is_set() and sentence_queue.empty()):
                    try:
                        sentence = sentence_queue.get(timeout=0.05)
                        full_text_list.append(sentence)
                        res_q: queue.Queue[Any] = queue.Queue()
                        job_queue.put(res_q)
                        executor.submit(_synthesize_job, sentence, res_q)
                    except queue.Empty:
                        continue
            except Exception as exc:
                logger.error("Synthesis coordinator error: %s", exc)

        fetch_thread = threading.Thread(target=_fetch_sentences, daemon=True)
        coord_thread = threading.Thread(target=_coordinating_synthesis, daemon=True)
        fetch_thread.start()
        coord_thread.start()

        while (
            not (finished_fetching.is_set() and (not coord_thread.is_alive()) and job_queue.empty())
            or not job_queue.empty()
            or coord_thread.is_alive()
        ):
            try:
                res_q = job_queue.get(timeout=0.05)
                is_sentence_start = True
                while True:
                    packet = res_q.get()
                    if packet is None:
                        break
                    if abort_event and abort_event.is_set():
                        break

                    if is_sentence_start and packet.get("audio_bytes"):
                        trimmed = self._trim_pcm_silence(packet["audio_bytes"], threshold=150)
                        if trimmed:
                            packet["audio_bytes"] = trimmed
                            is_sentence_start = False
                        else:
                            continue

                    if packet.get("audio_uri") or (
                        isinstance(packet.get("audio_bytes"), bytes) and len(packet.get("audio_bytes")) > 0
                    ):
                        on_audio_packet(packet)
                        if packet.get("audio_uri"):
                            followup_audio_uris.append(str(packet["audio_uri"]))
            except queue.Empty:
                if finished_fetching.is_set() and not coord_thread.is_alive() and job_queue.empty():
                    break
                continue

        executor.shutdown(wait=False)
        return "".join(full_text_list), followup_audio_uris, True

    def _run_llm_decision(
        self,
        *,
        session_id: str,
        transcript: str,
        confidence: float | None,
        language: str,
        interview_stage: str,
        question_id: str | None,
        llm_enabled: bool,
        tts_enabled: bool,
        tts_voice: str,
        decide_action: Callable[[str, float | None], tuple[str, str, list[str]]],
        build_rule_followup: Callable[[str, float | None, str, str, str | None], str | None],
        build_llm_followup: Callable[[str, float | None, str, str], str | None],
        on_audio_packet: Callable[[dict], None] | None,
        abort_event: threading.Event | None,
    ) -> _FollowupDecision:
        decision_start = time.perf_counter()
        action, decision_reason, decision_flags = decide_action(transcript, confidence)
        decision_latency_ms = int((time.perf_counter() - decision_start) * 1000)

        llm_latency_ms = 0
        followup_question: str | None = None
        followup_audio_uris: list[str] = []
        cache_hit = False
        streamed_in_llm_block = False
        degradation_mode: str | None = None
        warmup_future: concurrent.futures.Future | None = None
        warmup_executor: concurrent.futures.ThreadPoolExecutor | None = None

        if action in {"handoff", "blocked"}:
            return _FollowupDecision(
                action=action,
                decision_reason=decision_reason,
                decision_latency_ms=decision_latency_ms,
                policy_flags=list(decision_flags),
                followup_question=followup_question,
                followup_audio_uris=followup_audio_uris,
                cache_hit=cache_hit,
                llm_latency_ms=llm_latency_ms,
                degradation_mode=degradation_mode,
                streamed_in_llm_block=streamed_in_llm_block,
                warmup_future=warmup_future,
                warmup_executor=warmup_executor,
            )

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
                if tts_enabled and on_audio_packet:
                    text_stream = build_llm_followup(transcript, confidence, interview_stage, language)
                    if text_stream:
                        streamed_question, streamed_uris, streamed = self._stream_llm_followup_with_tts(
                            session_id=session_id,
                            text_stream=text_stream,
                            tts_voice=tts_voice,
                            on_audio_packet=on_audio_packet,
                            abort_event=abort_event,
                        )
                        followup_question = streamed_question
                        followup_audio_uris = streamed_uris
                        streamed_in_llm_block = streamed
                    else:
                        followup_question = ""
                else:
                    res = build_llm_followup(transcript, confidence, interview_stage, language)
                    if res is not None and not isinstance(res, str) and hasattr(res, "__iter__"):
                        followup_question = "".join(list(res))
                    else:
                        followup_question = res

                if followup_question:
                    DEFAULT_FOLLOWUP_CACHE.set(cache_key, question=followup_question, reason="llm")
            except Exception as llm_err:
                logger.error("LLM followup error: %s", llm_err, exc_info=True)
                followup_question = None
                degradation_mode = "llm_to_rule"
        llm_latency_ms = int((time.perf_counter() - llm_start) * 1000)

        if not followup_question:
            followup_question = build_rule_followup(transcript, confidence, interview_stage, language, action)
            if followup_question:
                DEFAULT_FOLLOWUP_CACHE.set(cache_key, question=followup_question, reason="rule")

        return _FollowupDecision(
            action=action,
            decision_reason=decision_reason,
            decision_latency_ms=decision_latency_ms,
            policy_flags=list(decision_flags),
            followup_question=followup_question,
            followup_audio_uris=followup_audio_uris,
            cache_hit=cache_hit,
            llm_latency_ms=llm_latency_ms,
            degradation_mode=degradation_mode,
            streamed_in_llm_block=streamed_in_llm_block,
            warmup_future=warmup_future,
            warmup_executor=warmup_executor,
        )

    def _run_tts_generation(
        self,
        *,
        session_id: str,
        followup_question: str | None,
        tts_enabled: bool,
        tts_voice: str,
        streamed_in_llm_block: bool,
        on_audio_packet: Callable[[dict], None] | None,
        abort_event: threading.Event | None,
        warmup_future: concurrent.futures.Future | None,
        degradation_mode: str | None,
    ) -> _TtsOutcome:
        followup_audio_uris: list[str] = []
        tts_start = time.perf_counter()
        next_degradation_mode = degradation_mode

        if followup_question and tts_enabled:
            if warmup_future is not None:
                try:
                    warmup_future.result(timeout=0.25)
                except Exception:
                    pass
            try:
                if not streamed_in_llm_block:
                    if on_audio_packet:
                        for packet in self._tts_provider.synthesize_stream_iter(
                            session_id=session_id,
                            text=followup_question,
                            voice=tts_voice,
                            chunk_size=24,
                        ):
                            if abort_event and abort_event.is_set():
                                break
                            on_audio_packet(packet)
                            if packet.get("audio_uri"):
                                followup_audio_uris.append(packet["audio_uri"])
                    else:
                        tts_result = self._tts_provider.synthesize_stream(
                            session_id=session_id,
                            text=followup_question,
                            voice=tts_voice,
                            chunk_size=24,
                        )
                        followup_audio_uris = list(tts_result.audio_uris)
            except Exception:
                followup_audio_uris = []
                next_degradation_mode = self._merge_degradation_mode(next_degradation_mode, "tts_to_text_only")

        tts_latency_ms = int((time.perf_counter() - tts_start) * 1000)
        return _TtsOutcome(
            followup_audio_uris=followup_audio_uris,
            tts_latency_ms=tts_latency_ms,
            degradation_mode=next_degradation_mode,
        )

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
        abort_event: threading.Event | None = None,
    ) -> OrchestratorResult:
        """串行处理候选人回合。如果提供了 on_audio_packet，则会尝试流式合成响应。"""
        logger.info(
            "[Orchestrator] Processing turn session=%s seq=%s transcript='%s' tts=%s llm=%s",
            session_id,
            seq,
            transcript_hint,
            tts_enabled,
            llm_enabled,
        )
        normalized = self._normalize_turn_input(
            session_id=session_id,
            seq=seq,
            transcript_hint=transcript_hint,
            audio_base64=audio_base64,
            confidence=confidence,
        )
        decision = self._run_llm_decision(
            session_id=session_id,
            transcript=normalized.transcript,
            confidence=confidence,
            language=language,
            interview_stage=interview_stage,
            question_id=question_id,
            llm_enabled=llm_enabled,
            tts_enabled=tts_enabled,
            tts_voice=tts_voice,
            decide_action=decide_action,
            build_rule_followup=build_rule_followup,
            build_llm_followup=build_llm_followup,
            on_audio_packet=on_audio_packet,
            abort_event=abort_event,
        )
        tts_outcome = self._run_tts_generation(
            session_id=session_id,
            followup_question=decision.followup_question,
            tts_enabled=tts_enabled,
            tts_voice=tts_voice,
            streamed_in_llm_block=decision.streamed_in_llm_block,
            on_audio_packet=on_audio_packet,
            abort_event=abort_event,
            warmup_future=decision.warmup_future,
            degradation_mode=decision.degradation_mode,
        )

        followup_audio_uris = list(decision.followup_audio_uris)
        if not decision.streamed_in_llm_block:
            followup_audio_uris = list(tts_outcome.followup_audio_uris)

        if decision.warmup_executor is not None:
            decision.warmup_executor.shutdown(wait=True, cancel_futures=True)

        # At turn end, clear ASR accumulated state to prevent cross-turn bleed-through
        try:
            self._asr_provider.flush(session_id=session_id)
        except Exception:
            pass

        e2e_latency_ms = (
            normalized.asr_latency_ms
            + decision.decision_latency_ms
            + decision.llm_latency_ms
            + tts_outcome.tts_latency_ms
        )
        return OrchestratorResult(
            transcript=normalized.transcript,
            action=decision.action,
            decision_reason=decision.decision_reason,
            policy_flags=list(decision.policy_flags),
            followup_question=decision.followup_question,
            followup_audio_uris=followup_audio_uris,
            degradation_mode=tts_outcome.degradation_mode,
            latency_breakdown={
                "asr_ms": normalized.asr_latency_ms,
                "decision_ms": decision.decision_latency_ms,
                "llm_ms": decision.llm_latency_ms,
                "tts_ms": tts_outcome.tts_latency_ms,
                "e2e_ms": e2e_latency_ms,
                "llm_cache_hit": 1 if decision.cache_hit else 0,
            },
        )
