"""Realtime orchestration: ASR -> policy -> follow-up -> TTS."""

from __future__ import annotations

import concurrent.futures
import time
import logging
import threading
import queue
from dataclasses import dataclass
from typing import Callable

from ...core.config import get_settings
from ..speech.base import ASRProvider, TTSProvider
from .followup_cache import DEFAULT_FOLLOWUP_CACHE
from .streaming_utils import split_sentences
import math
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
        # Note: To avoid duplicating the entire logic, we can keep the serial version
        # but integrate streaming inside it.
        degradation_mode: str | None = None
        followup_audio_uris: list[str] = []
        streamed_in_llm_block = False
        policy_flags: list[str] = []

        logger.info(f"[Orchestrator] Processing turn session={session_id} seq={seq} transcript='{transcript_hint}' tts={tts_enabled} llm={llm_enabled}")
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
                    # BE-013: Relaxed streaming check. If on_audio_packet is present, we assume the caller wants streaming if the provider/task allows it.
                    if tts_enabled and on_audio_packet:
                        # 流式路径：出一句合一句。使用生产者-消费者模式并发拉取 LLM 句子，减少句间延迟。
                        text_stream = build_llm_followup(transcript, confidence, interview_stage, language)
                        if text_stream:
                            sentence_queue = queue.Queue(maxsize=16)
                            job_queue = queue.Queue(maxsize=16)
                            full_text_list = []
                            finished_fetching = threading.Event()
                            executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

                            def _fetch_sentences():
                                try:
                                    for sentence in split_sentences(text_stream):
                                        if abort_event and abort_event.is_set():
                                            break
                                        sentence_queue.put(sentence)
                                except Exception as e:
                                    logger.error(f"Error fetching sentences from LLM: {e}")
                                finally:
                                    finished_fetching.set()

                            def _synthesize_job(sentence, res_q):
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
                                except Exception as e:
                                    logger.error(f"TTS Synthesis error for sentence '{sentence[:20]}': {e}")
                                finally:
                                    res_q.put(None) # Signal end of sentence

                            def _coordinating_synthesis():
                                try:
                                    while not (finished_fetching.is_set() and sentence_queue.empty()):
                                        try:
                                            sentence = sentence_queue.get(timeout=0.05)
                                            full_text_list.append(sentence)
                                            res_q = queue.Queue()
                                            job_queue.put(res_q)
                                            executor.submit(_synthesize_job, sentence, res_q)
                                        except queue.Empty:
                                            continue
                                except Exception as e:
                                    logger.error(f"Synthesis coordinator error: {e}")

                            fetch_thread = threading.Thread(target=_fetch_sentences, daemon=True)
                            coord_thread = threading.Thread(target=_coordinating_synthesis, daemon=True)
                            fetch_thread.start()
                            coord_thread.start()

                            streamed_in_llm_block = True
                            while not (finished_fetching.is_set() and (not coord_thread.is_alive()) and job_queue.empty()) or not job_queue.empty() or coord_thread.is_alive():
                                # Robust termination check: wait for coordination to finish AND jobs to be drained
                                try:
                                    res_q = job_queue.get(timeout=0.05)
                                    is_sentence_start = True
                                    while True:
                                        packet = res_q.get()
                                        if packet is None:
                                            break
                                        if abort_event and abort_event.is_set():
                                            break
                                        
                                        # 针对 PCM 编码进行首句去噪/去静音，让切换更无感
                                        if is_sentence_start and packet.get("audio_bytes"):
                                            # 只对每一句合出来的第一个包进行头部去静音
                                            trimmed = self._trim_pcm_silence(packet["audio_bytes"], threshold=150)
                                            if trimmed:
                                                packet["audio_bytes"] = trimmed
                                                is_sentence_start = False
                                            else:
                                                # 如果整包都是静音，继续等下一个包再切
                                                continue
                                        
                                        if packet.get("audio_uri") or (isinstance(packet.get("audio_bytes"), bytes) and len(packet.get("audio_bytes")) > 0):
                                            on_audio_packet(packet)
                                            if packet.get("audio_uri"):
                                                followup_audio_uris.append(str(packet["audio_uri"]))
                                except queue.Empty:
                                    if finished_fetching.is_set() and not coord_thread.is_alive() and job_queue.empty():
                                        break
                                    continue
                            
                            executor.shutdown(wait=False)
                            
                            followup_question = "".join(full_text_list)
                        else:
                            followup_question = ""
                    else:
                        res = build_llm_followup(transcript, confidence, interview_stage, language)
                        # Robust check for generators/iterators to avoid JSON serialization errors
                        if res is not None and not isinstance(res, str) and hasattr(res, "__iter__"):
                            followup_question = "".join(list(res))
                        else:
                            followup_question = res
                    
                    # if followup_question:
                    #     print(f"DEBUG [LLM Output] Session: {session_id}, Followup: {followup_question}")
                    
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
                        # 对于由于缓存命中或预取跳过 LLM 流的场景，不分句，直接全文合成以保证连贯性
                        # print(f"DEBUG [TTS Replay] Session: {session_id}, Playing existing followup: {followup_question[:100]}...")
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
