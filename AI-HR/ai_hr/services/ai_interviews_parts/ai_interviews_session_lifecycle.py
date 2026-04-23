from __future__ import annotations

from .ai_interviews_shared import *
from ..role_strategy import RoleProfiler


class AIInterviewSessionLifecycleMixin:
    def __init__(
        self,
        *,
        session_repository: AIInterviewSessionRepository,
        invitation_repository: AIInterviewInvitationRepository,
        runtime_repository: AIRuntimeRepository,
        candidate_repository: CandidateRepository,
        job_repository: JobRepository,
        interview_repository: InterviewRepository,
        event_repository: EventRepository,
        rtc_gateway: RTCGateway,
        asr_provider: ASRProvider,
        tts_provider: TTSProvider,
        llm_client: LLMClient,
        orchestrator: RealtimeOrchestrator,
        runtime_store: InterviewRuntimeStore,
        ten_runtime_manager: TENRuntimeManager | None = None,
    ):
        self._settings = get_settings()
        self._session_repository = session_repository
        self._invitation_repository = invitation_repository
        self._runtime_repository = runtime_repository
        self._candidate_repository = candidate_repository
        self._job_repository = job_repository
        self._interview_repository = interview_repository
        self._event_repository = event_repository
        self._rtc_gateway = rtc_gateway
        self._asr_provider = asr_provider
        self._tts_provider = tts_provider
        self._llm_client = llm_client
        self._llm_prefetch_client = LLMClient(
            router=ModelRouter(runtime_repository=None, settings=self._settings),
            guardrail_service=GuardrailService(),
            observability_repository=None,
        )
        self._orchestrator = orchestrator
        self._runtime_store = runtime_store
        self._assessment_service: EnterpriseAssessmentService = get_enterprise_assessment_service(session_repository._session)
        self._ten_runtime_manager = ten_runtime_manager or TENRuntimeManager(self._settings)
        self._question_flow_engine = InterviewQuestionFlowEngine()
        self._runtime_engine = InterviewRuntimeEngine(question_flow_engine=self._question_flow_engine)
        self._role_profiler = RoleProfiler()  # 初始化岗位识别器
        self._duplex_prefetch_lock = threading.Lock()
        self._duplex_prefetch_cache: dict[str, dict] = {}
        self._duplex_prefetch_inflight: set[str] = set()
        self._duplex_prefetch_abort_events: dict[str, threading.Event] = {}

    def create_invitation(self, candidate_id: str, job_id: str, note: str | None = None) -> AIInterviewInvitationResponse:
        """创建面试邀请链接并触发题目预生成。"""
        # 0. Validate candidate and job existence
        candidate = self._candidate_repository.get(candidate_id)
        job = self._job_repository.get(job_id)
        role_context = self._resolve_role_context(candidate=candidate, job=job, persisted_payload=None)

        # 1. Generate token and expiration (3 days)
        token = uuid.uuid4().hex
        expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=3)

        # 2. Create invitation record
        entity = self._invitation_repository.create(
            candidate_id=candidate_id,
            job_id=job_id,
            token=token,
            expires_at=expires_at,
            payload=self._build_role_payload_patch(role_context),
            note=note
        )

        # 3. Trigger question generation immediately
        try:
            # Pass invitation_id with an empty session_id
            self.generate_question_set(invitation_id=entity.id)
            self._invitation_repository.update_status(entity.id, "ready")
        except Exception as e:
            logger.error("Failed to auto-generate questions for invitation %s: %s", entity.id, e)
            # Keep pending status and retry generation on later access

        return AIInterviewInvitationResponse(
            id=entity.id,
            token=entity.token,
            candidate_id=entity.candidate_id,
            job_id=entity.job_id,
            status=entity.status,
            expires_at=entity.expires_at,
            job_title=job.title or "Unknown"
        )

    def get_invitation_by_token(self, token: str) -> AIInterviewInvitationResponse:
        """获取邀请链接详情并校验。"""
        entity = self._invitation_repository.get_by_token(token)
        now = datetime.now(UTC).replace(tzinfo=None)
        
        if entity.expires_at < now:
            self._invitation_repository.update_status(entity.id, "expired")
            raise InvalidStateError(f"Invitation link with token '{token}' has expired")
            
        job = self._job_repository.get(entity.job_id)
        return AIInterviewInvitationResponse(
            id=entity.id,
            token=entity.token,
            candidate_id=entity.candidate_id,
            job_id=entity.job_id,
            status=entity.status,
            expires_at=entity.expires_at,
            job_title=job.title or "Unknown"
        )

    def activate_invitation(self, token: str, operator: str = "candidate") -> dict:
        """通过邀请链接激活面试，创建新 Session。"""
        invitation = self._invitation_repository.get_by_token(token)
        now = datetime.now(UTC).replace(tzinfo=None)
        
        # 1. Strict validation: expiration and one-time-use constraints
        if invitation.expires_at < now:
            self._invitation_repository.update_status(invitation.id, "expired")
            raise InvalidStateError("邀请链接已过期 (Expired)")
            
        if invitation.used_count >= invitation.max_use_count:
            raise InvalidStateError(f"邀请链接已达到最大使用次数 ({invitation.max_use_count})")

        # 2. Create a brand-new session (even if one existed before)
        session_create_req = AIInterviewSessionCreateRequest(
            candidate_id=invitation.candidate_id,
            job_id=invitation.job_id,
            channel="invitation_link",
            language="zh-CN",
            note=invitation.note,
            explicit_role_id=str(self._extract_role_payload(invitation.payload or {}).get("id") or "").strip() or None,
            payload={
                "invitation_token": token,
                **self._build_role_payload_patch({"payload": {"role": self._extract_role_payload(invitation.payload or {})}}),
            }
        )
        session_dict = self.create_session(session_create_req)
        session_id = session_dict["id"]

        # 3. Check prebuilt question pack and attach it to the new session
        prebuilt_set = self._session_repository.get_latest_question_set(invitation_id=invitation.id)
        if prebuilt_set:
            version = self._session_repository.get_latest_question_set_version(session_id) + 1
            self._session_repository.create_question_set(
                session_id=session_id,
                invitation_id=invitation.id,
                version=version,
                source=prebuilt_set.source,
                questions=prebuilt_set.questions_json
            )
            
        # 4. Critical: mark invite link as activated (increment usage count)
        self._invitation_repository.mark_activated(invitation.id)

        # 5. Start session
        start_req = AIInterviewSessionStartRequest(operator=operator)
        return self.start_session(session_id, start_req)

    def create_session(self, payload: AIInterviewSessionCreateRequest) -> dict:
        """Cleaned docstring."""
        candidate = self._candidate_repository.get(payload.candidate_id)
        job = self._job_repository.get(payload.job_id)
        role_context = self._resolve_role_context(
            candidate=candidate,
            job=job,
            explicit_role_id=getattr(payload, "explicit_role_id", None),
            persisted_payload=dict(payload.payload or {}),
        )

        join_token = uuid.uuid4().hex
        rtc_room_id = f"ai-intv-{uuid.uuid4()}"
        rtc_info = self._rtc_gateway.create_room(session_id=f"{payload.candidate_id}:{payload.job_id}", preferred_room_id=rtc_room_id)

        runtime_company_payload = self._build_runtime_company_payload(
            job_id=payload.job_id,
            job_requirements=job.requirements or "",
            payload=dict(payload.payload),
        )

        entity = self._session_repository.create(
            candidate_id=payload.candidate_id,
            job_id=payload.job_id,
            channel=payload.channel,
            language=payload.language,
            rtc_room_id=rtc_info.room_id,
            join_token=rtc_info.join_token or join_token,
            note=payload.note,
            payload={
                "interview_stage": InterviewStage.OPENING,
                **self._build_rtc_payload(rtc_info),
                **runtime_company_payload,
                **self._build_role_payload_patch(role_context),
                **dict(payload.payload),
            },
        )
        entity = self._session_repository.update_status(
            entity.id,
            status=entity.status,
            payload_patch={
                "ten_enabled": bool(self._settings.ai_interview_ten_enabled),
                "ten_launch_status": "pending_start" if self._settings.ai_interview_ten_enabled else "disabled",
            },
        )
        return self._to_session_dict(entity)

    def get_session(self, session_id: str) -> dict:
        """Cleaned docstring."""
        entity = self._session_repository.get(session_id)
        return self._to_session_dict(entity)

    def start_session(self, session_id: str, payload: AIInterviewSessionStartRequest) -> dict:
        """Cleaned docstring."""
        entity = self._session_repository.get(session_id)
        if entity.status != InterviewSessionStatus.CREATED:
            raise InvalidStateError(f"AI interview session '{session_id}' cannot start from status '{entity.status}'")
        
        try:
            hydrated_role_config = self._hydrate_session_role_config(
                session_id=session_id,
                persisted_payload=dict(entity.payload or {}),
            )
            if hydrated_role_config:
                logger.info(
                    "ai_interview.role_config_set session_id=%s role_id=%s",
                    session_id,
                    hydrated_role_config.get("role", {}).get("id"),
                )
        except Exception as e:
            logger.warning(
                "ai_interview.role_config_set_failed session_id=%s error=%s",
                session_id,
                str(e),
            )
        
        # Prewarm ASR/TTS connection to reduce first-turn latency spikes.
        self.asr_warmup(session_id=session_id)
        self.tts_warmup(session_id=session_id, voice=DEFAULT_TTS_VOICE)
        
        prebuilt_patch = self._attach_prebuilt_question_pack(session_id=session_id)
        payload_patch = {"last_operator": payload.operator}
        payload_patch.update(prebuilt_patch)
        question_pack = self._ensure_runtime_question_pack_for_start(session_id=session_id)
        if question_pack:
            state = self._reset_runtime_state_for_start(session_id=session_id, question_pack=question_pack)
            payload_patch[PayloadKey.INTERVIEW_STAGE] = self._question_flow_engine.derive_stage(
                state=state,
                question_pack=question_pack,
            )
            payload_patch["question_pack"] = question_pack
            payload_patch["question_count"] = int(question_pack.get("question_count") or 0)
            payload_patch["question_pack_version"] = int(question_pack.get("version") or 0)
            payload_patch["question_pack_source"] = str(
                question_pack.get("source") or payload_patch.get("question_pack_source") or ""
            )
        else:
            logger.error(
                "ai_interview.start_session_question_pack_unavailable session_id=%s",
                session_id,
            )
        entity = self._session_repository.update_status(
            session_id,
            status=InterviewSessionStatus.IN_PROGRESS,
            payload_patch=payload_patch,
        )
        ten_patch = self._prepare_ten_runtime(entity)
        if ten_patch:
            entity = self._session_repository.update_status(
                entity.id,
                status=entity.status,
                payload_patch=ten_patch,
            )
        if question_pack:
            self._log_runtime_start_snapshot(session_id=session_id, question_pack=question_pack)
        return self._to_session_dict(entity)

    def asr_warmup(self, session_id: str) -> None:
        """Cleaned docstring."""
        try:
            self._asr_provider.warmup(session_id=session_id)
        except Exception:
            pass

    def tts_warmup(self, session_id: str, voice: str = DEFAULT_TTS_VOICE) -> None:
        """Cleaned docstring."""
        try:
            self._tts_provider.warmup(session_id=session_id, voice=voice)
        except Exception:
            pass

    def finish_session(self, session_id: str, payload: AIInterviewSessionFinishRequest) -> dict:
        """Cleaned docstring."""
        entity = self._session_repository.get(session_id)
        if entity.status != InterviewSessionStatus.IN_PROGRESS:
            raise InvalidStateError(f"AI interview session '{session_id}' cannot finish from status '{entity.status}'")
        
        # Clear role config for session (prevent memory leaks)
        from ..interview_runtime.flow_policy import clear_role_config_for_session
        clear_role_config_for_session(session_id)
        
        entity = self._session_repository.update_status(
            session_id,
            status=payload.result_status,
            note=payload.note,
            payload_patch={"finish_operator": payload.operator, PayloadKey.INTERVIEW_STAGE: InterviewStage.CLOSING},
        )
        return self._to_session_dict(entity)

    def handoff_session(self, session_id: str, payload: AIInterviewSessionHandoffRequest) -> dict:
        """Cleaned docstring."""
        entity = self._session_repository.get(session_id)
        if entity.status != InterviewSessionStatus.IN_PROGRESS:
            raise InvalidStateError(f"AI interview session '{session_id}' cannot handoff from status '{entity.status}'")

        # Clear role config for session (prevent memory leaks)
        from ..interview_runtime.flow_policy import clear_role_config_for_session
        clear_role_config_for_session(session_id)

        handoff = self._session_repository.create_handoff(
            session_id=session_id,
            reason=payload.reason,
            trigger_flags=payload.trigger_flags,
            operator=payload.operator,
            note=payload.note,
            payload=payload.payload,
        )
        entity = self._session_repository.update_status(
            session_id,
            status=InterviewSessionStatus.FAILED,
            payload_patch={
                "handoff_id": handoff.id,
                PayloadKey.HANDOFF_REASON: payload.reason,
                "handoff_operator": payload.operator,
            },
        )
        return {
            "session": self._to_session_dict(entity),
            "handoff_id": handoff.id,
        }

    def append_event(self, session_id: str, payload: AIInterviewSessionEventRequest) -> dict:
        """Cleaned docstring."""
        entity = self._session_repository.get(session_id)
        if entity.status != InterviewSessionStatus.IN_PROGRESS:
            raise InvalidStateError(f"AI interview session '{session_id}' cannot accept events from status '{entity.status}'")

        self._hydrate_session_role_config(session_id=session_id, persisted_payload=dict(entity.payload or {}))

        action: str | None = None
        decision_reason: str | None = None
        decision_flags: list[str] = []
        followup_question: str | None = None
        followup_audio_uris: list[str] = []
        interview_stage: str | None = None
        runtime_mode = self._resolve_runtime_mode()
        model_route = self._resolve_model_route(session_id)
        degradation_mode: str | None = None
        latency_breakdown: dict[str, int] = {}
        effective_transcript = payload.transcript
        effective_confidence = payload.confidence
        question_attempt_id: str | None = None
        resolved_question_id = str((payload.payload or {}).get("current_question_id") or (payload.payload or {}).get("question_id") or "").strip() or None
        resolved_question_seq_raw = (payload.payload or {}).get("current_question_seq") or (payload.payload or {}).get("question_seq")
        try:
            resolved_question_seq = int(resolved_question_seq_raw) if resolved_question_seq_raw is not None else None
        except (TypeError, ValueError):
            resolved_question_seq = None
        ingest_trace_id = str((payload.payload or {}).get("trace_id") or "").strip() or None
        
        # 1. Robust Deduplication (Seq-level)
        # Prevents redundant LLM triggers from both ASR Final and EOT Flush for the same turn.
        with _DUPLEX_FINALIZE_LOCK:
            if session_id not in _DUPLEX_FINALIZED_SEQ:
                _DUPLEX_FINALIZED_SEQ[session_id] = set()
            seq_set = _DUPLEX_FINALIZED_SEQ[session_id]
            
            if payload.seq in seq_set:
                logger.info(f"[Deduplication] Session {session_id} Seq {payload.seq} already finalized/processed. Skipping.")
                return {
                    "session_id": session_id,
                    "event_id": payload.event_id,
                    "accepted": False,
                    "deduplicated": True,
                    "turn_id": None,
                    "action": None,
                    "decision_reason": "already_finalized",
                }

            # Only mark as finalized if we are processing a candidate's authoritative turn
            if payload.speaker == SpeakerRole.CANDIDATE and (payload.transcript or "").strip():
                # We only mark it as fully 'done' if we are about to trigger the orchestrator
                # Note: seq is added to the set after we are SURE this is a meaningful final turn.
                seq_set.add(payload.seq)

        if self._session_repository.is_event_seen(session_id=session_id, event_id=payload.event_id):
            return {
                "session_id": session_id,
                "event_id": payload.event_id,
                "accepted": False,
                "deduplicated": True,
                "turn_id": None,
                "action": None,
                "decision_reason": None,
                "policy_flags": [],
                PayloadKey.INTERVIEW_STAGE: None,
                PayloadKey.FOLLOWUP_QUESTION: None,
                "followup_audio_uris": [],
                PayloadKey.RUNTIME_MODE: runtime_mode,
                "model_route": model_route,
                PayloadKey.DEGRADATION_MODE: None,
                PayloadKey.LATENCY_BREAKDOWN: {},
            }

        if payload.speaker == SpeakerRole.CANDIDATE:
            # logger.debug(f"DEBUG [append_event] Processing candidate turn: session={session_id} seq={payload.seq}")
            duplex_mode = bool((payload.payload or {}).get("duplex_mode"))
            prefetched_followup = str((payload.payload or {}).get("prefetched_followup_question") or "").strip()
            prefetched_llm_ms = int((payload.payload or {}).get("prefetched_llm_ms") or 0)
            prefetched_from_partial = bool((payload.payload or {}).get("prefetched_from_partial"))
            
            question_pack = self._runtime_store.get_question_pack(session_id=session_id)
            active_question = self._get_active_question_context(session_id=session_id) if question_pack else None
            active_question_id = None
            if isinstance(active_question, dict):
                raw_qid = active_question.get("id") or active_question.get("index")
                if raw_qid is not None:
                    active_question_id = str(raw_qid)
            if not resolved_question_id and active_question_id:
                resolved_question_id = active_question_id
            if resolved_question_seq is None and isinstance(active_question, dict):
                raw_seq = active_question.get("index")
                try:
                    resolved_question_seq = int(raw_seq) if raw_seq is not None else None
                except (TypeError, ValueError):
                    resolved_question_seq = None
            
            if question_pack:
                state = self._load_or_init_runtime_state(session_id=session_id, question_pack=question_pack)
                interview_stage = self._advance_stage_by_question_flow(session_id=session_id, state=state)
            else:
                interview_stage = self._advance_stage(session_id)

            def _on_audio_packet(packet: dict) -> None:
                """将 TTS 分片推送至事件总线并打印调试。"""
                if packet.get("audio_bytes") and not packet.get("_first_pcm_marker_recorded"):
                    packet["tts_first_pcm_at_ms"] = _record_duplex_timeline_marker(
                        session_id=session_id,
                        seq=payload.seq,
                        marker_key="tts_first_pcm_at_ms",
                    )
                    packet["_first_pcm_marker_recorded"] = True
                DEFAULT_INTERVIEW_EVENT_BUS.publish(
                    session_id=session_id,
                    event_type=InterviewEventType.TTS_PACKET,
                    payload=packet,
                )

            def llm_stream_wrapper(t, c, s, l):
                return self._build_followup_question_with_llm(
                    session_id=session_id,
                    seq=payload.seq,
                    transcript=t,
                    confidence=c,
                    interview_stage=s,
                    language=l,
                    write_observability=True,
                    abort_event=None,
                    print_stream=True,
                )
            llm_stream_wrapper.is_streaming = True

            orchestrated = self._orchestrator.process_candidate_turn(
                session_id=session_id,
                seq=payload.seq,
                transcript_hint=payload.transcript or "",
                audio_base64=payload.audio_base64,
                confidence=payload.confidence,
                language=entity.language,
                runtime_mode=runtime_mode,
                llm_enabled=self._is_interview_llm_enabled() and not prefetched_followup,
                decide_action=lambda transcript, confidence: self._decide_interview_action(
                    session_id=session_id,
                    transcript=transcript,
                    confidence=confidence,
                ),
                build_rule_followup=lambda transcript, confidence, stage, language, action: self._build_followup_question(
                    transcript=transcript,
                    confidence=confidence,
                    interview_stage=stage,
                    language=language,
                    action=action,
                ),
                build_llm_followup=llm_stream_wrapper,
                interview_stage=interview_stage,
                question_id=active_question_id,
                followup_question=prefetched_followup if prefetched_followup else None,
                tts_enabled=not duplex_mode,
                on_audio_packet=_on_audio_packet,
            )
            effective_transcript = orchestrated.transcript
            action = orchestrated.action
            decision_reason = orchestrated.decision_reason
            decision_flags = orchestrated.policy_flags
            followup_question = orchestrated.followup_question
            followup_audio_uris = orchestrated.followup_audio_uris
            degradation_mode = orchestrated.degradation_mode
            latency_breakdown = orchestrated.latency_breakdown

            if prefetched_followup and action not in {InterviewAction.HANDOFF, InterviewAction.BLOCKED}:
                followup_question = prefetched_followup
                original_llm_ms = int(latency_breakdown.get("llm_ms") or 0)
                latency_breakdown["llm_ms"] = 0
                latency_breakdown["llm_prefetch_hit"] = 1
                latency_breakdown["llm_prefetch_ms"] = max(0, prefetched_llm_ms)
                latency_breakdown["e2e_ms"] = max(1, int(latency_breakdown.get("e2e_ms") or 0) - original_llm_ms)
                if prefetched_from_partial:
                    decision_flags = [*decision_flags, LLM_PREFETCH_FROM_PARTIAL_FLAG]
            if followup_question and action not in {InterviewAction.HANDOFF, InterviewAction.BLOCKED}:
                followup_question = self._attach_followup_ack_prefix(
                    followup_question,
                    language=entity.language,
                )

            latency_breakdown.update(self._build_turn_timeline_breakdown(session_id=session_id, seq=payload.seq))

            effective_confidence = payload.confidence if payload.confidence is not None else 0.9
            if question_pack and action not in {InterviewAction.HANDOFF, InterviewAction.BLOCKED}:
                flow_result = self._update_question_flow_after_turn(
                    session_id=session_id,
                    transcript=effective_transcript or "",
                    confidence=effective_confidence,
                    question_pack=question_pack,
                )
                if flow_result.get(PayloadKey.INTERVIEW_STAGE):
                    interview_stage = flow_result[PayloadKey.INTERVIEW_STAGE]
                if flow_result.get("need_followup"):
                    decision_flags = [*decision_flags, INSUFFICIENT_EVIDENCE_FLAG]
                    decision_reason = flow_result.get("reason") or decision_reason

        turn, deduplicated = self._session_repository.create_turn_event(
            session_id=session_id,
            event_id=payload.event_id,
            speaker=payload.speaker,
            transcript=effective_transcript,
            audio_uri=payload.audio_uri,
            confidence=effective_confidence,
            latency_ms=latency_breakdown.get("e2e_ms", payload.latency_ms),
            question_attempt_id=None,
            question_id=resolved_question_id,
            question_seq=resolved_question_seq,
            ingest_trace_id=ingest_trace_id,
            policy_flags=payload.policy_flags + decision_flags,
            payload={
                **payload.payload,
                PayloadKey.LATENCY_BREAKDOWN: latency_breakdown,
                PayloadKey.DEGRADATION_MODE: degradation_mode,
                PayloadKey.FOLLOWUP_QUESTION: followup_question,
                PayloadKey.INTERVIEW_STAGE: interview_stage,
            },
            transcript_ttl_days=180,
            audio_ttl_days=30,
        )
        if turn is not None and not deduplicated:
            question_attempt_id = self._assessment_service.bind_question_answer_from_turn(
                session_id=session_id,
                turn=turn,
                request_payload=dict(payload.payload or {}),
                interview_stage=interview_stage,
                commit=True,
            )

        DEFAULT_INTERVIEW_EVENT_BUS.publish(
            session_id=session_id,
            event_type="session.event",
            payload={
                "event_id": payload.event_id,
                "turn_id": turn.id if turn else None,
                "speaker": payload.speaker,
                "transcript": effective_transcript,
                "accepted": not deduplicated,
                "deduplicated": deduplicated,
                PayloadKey.FOLLOWUP_QUESTION: followup_question,
                "followup_audio_uris": followup_audio_uris,
                "action": action,
                "decision_reason": decision_reason,
                PayloadKey.LATENCY_BREAKDOWN: latency_breakdown,
            },
        )
        return {
            "session_id": session_id,
            "event_id": payload.event_id,
            "accepted": not deduplicated,
            "deduplicated": deduplicated,
            "turn_id": turn.id if turn else None,
            "question_attempt_id": question_attempt_id,
            "action": action,
            "decision_reason": decision_reason,
            "policy_flags": payload.policy_flags + decision_flags,
            PayloadKey.INTERVIEW_STAGE: interview_stage,
            PayloadKey.FOLLOWUP_QUESTION: followup_question,
            "followup_audio_uris": followup_audio_uris,
            PayloadKey.RUNTIME_MODE: runtime_mode,
            "model_route": model_route,
            PayloadKey.DEGRADATION_MODE: degradation_mode,
            PayloadKey.LATENCY_BREAKDOWN: latency_breakdown,
        }

    def record_client_playback_mark(
        self,
        *,
        session_id: str,
        seq: int,
        packet_index: int | None = None,
        client_ts_ms: int | None = None,
        transport: str | None = None,
    ) -> dict[str, int | str]:
        entity = self._session_repository.get(session_id)
        played_at_ms = _record_duplex_timeline_marker(
            session_id=session_id,
            seq=seq,
            marker_key="client_first_play_at_ms",
            at_ms=client_ts_ms,
        )
        markers = self._build_turn_timeline_breakdown(session_id=session_id, seq=seq)
        self._event_repository.create(
            event_type="ai_interview.rtc.client_playback",
            entity_type="ai_interview_session",
            entity_id=session_id,
            status="success",
            operator="candidate_client",
            session_id=session_id,
            job_id=entity.job_id,
            payload={
                "seq": seq,
                "packet_index": packet_index,
                "client_first_play_at_ms": played_at_ms,
                "transport": transport or "binary",
                PayloadKey.LATENCY_BREAKDOWN: markers,
            },
        )
        return {
            "session_id": session_id,
            "seq": int(seq),
            "client_first_play_at_ms": int(played_at_ms),
        }

