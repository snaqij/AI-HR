from __future__ import annotations

from .ai_interviews_shared import (
    AIInterviewASRStreamRequest,
    AIInterviewASRStreamResponse,
    AIInterviewSessionEventRequest,
    DEFAULT_INTERVIEW_EVENT_BUS,
    DEFAULT_TTS_VOICE,
    InterviewEventType,
    InterviewStageGroup,
    PayloadKey,
    SpeakerRole,
    _record_duplex_timeline_marker,
    get_ai_interview_service,
    hashlib,
    logger,
    threading,
    time,
)


class AIInterviewAudioDuplexMixin:
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
                    logger.debug(
                        "ai_interview.duplex.asr_dedup_drop trace_id=%s session_id=%s frame_id=%s",
                        session_id,
                        session_id,
                        frame_id,
                    )
                    return {
                        "session_id": session_id,
                        "seq": seq,
                        "chunk_index": chunk_index,
                        "frame_id": frame_id,
                        "deduplicated": True,
                    }
                
                seen.add(frame_id)
                if len(seen) > 1000:
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
            # If AIInterviewASRStreamRequest supports audio_bytes, set it for provider-level optimizations.
            if hasattr(asr_req, "audio_bytes"):
                setattr(asr_req, "audio_bytes", audio_bytes)

            logger.debug(
                "ai_interview.duplex.asr_ingest trace_id=%s session_id=%s audio_len=%s",
                session_id,
                session_id,
                len(audio_bytes or payload.get("audio_base64") or ""),
            )
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

            with self._duplex_prefetch_lock:
                old_event = self._duplex_prefetch_abort_events.get(session_id)
                if old_event:
                    old_event.set()
                abort_event = threading.Event()
                self._duplex_prefetch_abort_events[session_id] = abort_event
                self._duplex_prefetch_inflight.add(inflight_key)

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
                except Exception:
                    pass
                
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
            except Exception:
                pass

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
                            logger.debug(
                                "ai_interview.llm.stream_chunk trace_id=%s session_id=%s chunk=%s",
                                session_id,
                                session_id,
                                chunk,
                            )
                        followup_list.append(chunk)
                    logger.debug("ai_interview.llm.stream_end trace_id=%s session_id=%s", session_id, session_id)
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
        """Cleaned docstring."""
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

                def llm_stream_wrapper(t, c, s, language_code):
                    return worker_service._build_followup_question_with_llm(
                        session_id=session_id,
                        seq=seq,
                        transcript=t,
                        confidence=c,
                        interview_stage=s,
                        language=language_code,
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

