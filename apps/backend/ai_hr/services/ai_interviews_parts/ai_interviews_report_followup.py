from __future__ import annotations

import random

from .ai_interviews_shared import (
    AIInterviewMetricsResponse,
    AIInterviewReplayResponse,
    AIInterviewReportResponse,
    BlockReason,
    DEFAULT_INTERVIEW_EVENT_BUS,
    FOLLOWUP_DEFAULT_QUESTION,
    FOLLOWUP_DEFAULT_SIGNAL,
    FOLLOWUP_SPEAKER_AI,
    FOLLOWUP_SPEAKER_CANDIDATE,
    Generator,
    HandoffReason,
    InterviewAction,
    InterviewEventType,
    InterviewSessionStatus,
    InterviewStage,
    InterviewStageGroup,
    InvokeContext,
    LOW_CONFIDENCE_FLAG,
    PayloadKey,
    PromptTaskKey,
    PromptTemplate,
    RuntimeMode,
    SpeakerRole,
    _get_duplex_timeline_markers,
    _record_duplex_timeline_marker,
    build_sensitive_flag,
    get_prompt_template,
    logger,
    threading,
    uuid,
)


class AIInterviewReportFollowupMixin:
    _FOLLOWUP_ACK_PREFIXES_ZH = (
        "好的，我了解了。",
        "明白，你的回答我理解了。",
        "嗯，我理解你的思路了。",
    )
    _FOLLOWUP_ACK_PREFIXES_EN = (
        "Got it, thanks for the context. ",
        "Understood, that is clear. ",
        "I see what you mean. ",
        "Thanks, that helps. ",
    )

    @classmethod
    def _looks_like_ack_prefixed(cls, text: str, *, language: str) -> bool:
        normalized = str(text or "").strip().lower()
        if not normalized:
            return False
        if language == "en-US":
            return normalized.startswith(("got it", "understood", "i see", "thanks"))
        return normalized.startswith(("好的", "明白", "嗯", "了解"))

    @classmethod
    def _attach_followup_ack_prefix(cls, text: str, *, language: str) -> str:
        normalized = str(text or "").strip()
        if not normalized:
            return ""
        if cls._looks_like_ack_prefixed(normalized, language=language):
            return normalized
        prefix_pool = cls._FOLLOWUP_ACK_PREFIXES_EN if language == "en-US" else cls._FOLLOWUP_ACK_PREFIXES_ZH
        return f"{random.choice(prefix_pool)}{normalized}"

    def get_report(
        self,
        session_id: str,
        *,
        run_id: str | None = None,
        force_recompute: bool = False,
    ) -> AIInterviewReportResponse:
        """Cleaned docstring."""
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
        """Cleaned docstring."""
        self._session_repository.get(session_id)
        turns = self._session_repository.list_turns(session_id)
        paged = turns[max(0, offset) : max(0, offset) + max(1, min(limit, 200))]
        items = [
            {
                "turn_id": item.id,
                "turn_no": item.turn_no,
                "speaker": item.speaker,
                "question_id": item.question_id,
                "question_seq": item.question_seq,
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
        """Cleaned docstring."""
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
        """Cleaned docstring."""
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
                    next_q_text = f"\n备用下一个正式问题：{next_q.get('question')}\n"
        except Exception:
            pass

        return {
            "language": language,
            "stage": interview_stage,
            "current_question": current_question,
            "expected_signal": expected_signal,
            "answer": compact_answer,
            "last_turns_summary": " | ".join(summaries) if summaries else "无历史上下文",
            "confidence": f"{confidence:.2f}" if confidence is not None else "",
            "next_question_section": next_q_text,
            "stage_hint": "当前是 S2 暖场阶段，请保持简洁。如果候选人已提供基本背景，请尽快引导至技术深挖，避免重复确认职责。" if interview_stage == "S2" else "",
        }

    def _decide_interview_action(self, *, session_id: str, transcript: str, confidence: float | None) -> tuple[str, str, list[str]]:
        """Cleaned docstring."""
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
        """Cleaned docstring."""
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
        """Cleaned docstring."""
        if action in {InterviewAction.HANDOFF, InterviewAction.BLOCKED}:
            return None
        if confidence is not None and confidence < 0.60:
            if language == "en-US":
                prompt = "Please answer with one concrete case, including context, actions, and measurable result."
            else:
                prompt = "请用一个具体案例补充你的回答，包含背景、行动与结果。"
            return self._attach_followup_ack_prefix(prompt, language=language)
        if len((transcript or "").strip()) < 18:
            if language == "en-US":
                prompt = f"We are in {interview_stage or InterviewStageGroup.CORE} stage, please add more detail and measurable outcomes."
            else:
                prompt = f"当前处于 {interview_stage or InterviewStageGroup.CORE} 阶段，请补充更多细节和量化结果。"
            return self._attach_followup_ack_prefix(prompt, language=language)
        return None

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
        
        # Wrap LLM stream with split_sentences
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
        is_first_sentence = True
        for sentence in split_sentences(text_stream):
            if abort_event and abort_event.is_set():
                logger.info(f"Speculative LLM task aborted for session={session_id}")
                return
            if is_first_sentence:
                sentence = self._attach_followup_ack_prefix(sentence, language=language)
                is_first_sentence = False
            if emit_delta:
                DEFAULT_INTERVIEW_EVENT_BUS.publish(
                    session_id=session_id,
                    event_type=InterviewEventType.LLM_SENTENCE,
                    payload={"text": sentence, "is_final": False}
                )
            if print_stream:
                logger.debug(
                    "ai_interview.llm.speculative_sentence trace_id=%s session_id=%s sentence=%s",
                    session_id,
                    session_id,
                    sentence,
                )
            yield sentence

