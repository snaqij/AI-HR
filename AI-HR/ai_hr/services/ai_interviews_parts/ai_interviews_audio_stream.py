from __future__ import annotations

from .ai_interviews_shared import *


class AIInterviewAudioStreamMixin:
    def rtc_ingest_audio(self, payload: AIInterviewRTCASRIngestRequest) -> dict:
        """RTC-002B/003B: ingest room audio frame then optionally trigger followup + TTS publish."""
        session_entity = self._session_repository.get_by_room_id(payload.room_id)
        if session_entity is None:
            raise InvalidStateError(f"room_id '{payload.room_id}' is not linked to any AI interview session")

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
        """Cleaned docstring."""
        entity = self._session_repository.get(session_id)
        audio_bytes = getattr(payload, "audio_bytes", None)
        if self._settings.asr_force_streaming and not (payload.audio_base64 or audio_bytes) and not payload.is_final:
            raise InvalidStateError("ASR force_streaming 已开启，音频数据不能为空")
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
        """Cleaned docstring."""
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
        """Cleaned docstring."""
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
                # Debug hook reserved for tracing append_event trigger timing.
                self.append_event(session_id, event_req)
        except Exception as e:
            logger.warning(f"Error in _safe_flush_asr for session={session_id}: {e}")

