from __future__ import annotations

from .ai_interviews_shared import (
    AIInterviewRTCAudioSubscribeRequest,
    AIInterviewRTCAudioSubscribeResponse,
    AIInterviewRTCJoinRequest,
    AIInterviewRTCJoinResponse,
    AIInterviewRTCReconnectRequest,
    AIInterviewRTCReconnectResponse,
    AIInterviewRTCVideoPolicyRequest,
    AIInterviewRTCVideoPolicyResponse,
    AIInterviewTENRuntimeResponse,
    InterviewSessionStatus,
    InvalidStateError,
    logger,
)


class AIInterviewSessionRTCOpsMixin:
    def rtc_join(self, session_id: str, payload: AIInterviewRTCJoinRequest) -> AIInterviewRTCJoinResponse:
        """Cleaned docstring."""
        entity = self._session_repository.get(session_id)
        self._ensure_session_active_for_realtime(entity, action="rtc_join")
        if payload.candidate_id != entity.candidate_id:
            raise InvalidStateError("candidate_id 与会话不匹配")
        join_info = self._rtc_gateway.join_room(
            session_id=session_id,
            room_id=entity.rtc_room_id,
            client_id=payload.client_id,
            candidate_id=payload.candidate_id,
            join_token=entity.join_token,
        )
        updated_entity = self._session_repository.update_status(
            session_id,
            status=entity.status,
            payload_patch={
                "rtc_client_id": payload.client_id,
                "rtc_joined": True,
                **self._build_rtc_payload(join_info),
            },
        )
        ten_patch = self._prepare_ten_runtime(updated_entity, rtc_override=join_info)
        if ten_patch:
            updated_entity = self._session_repository.update_status(
                session_id,
                status=updated_entity.status,
                payload_patch=ten_patch,
            )
            updated_entity = self._maybe_auto_launch_ten(updated_entity)
        self._event_repository.create(
            event_type="ai_interview.rtc.join",
            entity_type="ai_interview_session",
            entity_id=session_id,
            status="success",
            operator="candidate",
            session_id=session_id,
            job_id=entity.job_id,
            payload={"client_id": payload.client_id, "transport": join_info.transport, "vendor": join_info.vendor},
        )
        return AIInterviewRTCJoinResponse(
            session_id=session_id,
            provider=join_info.vendor,
            room_id=join_info.room_id,
            channel_name=join_info.channel_name or join_info.room_id,
            join_token=join_info.join_token,
            app_id=join_info.app_id,
            uid=join_info.uid,
            expire_at=join_info.expire_at,
            reconnectable=True,
            transport=join_info.transport,
        )

    def get_ten_runtime_config(self, session_id: str) -> AIInterviewTENRuntimeResponse:
        entity = self._session_repository.get(session_id)
        self._ensure_session_active_for_realtime(entity, action="ten_runtime_config")
        response = AIInterviewTENRuntimeResponse.model_validate(self._build_ten_runtime_response(entity))
        if response.launch_command:
            logger.info(
                "ai_interview.ten.command_ready trace_id=%s session_id=%s candidate_id=%s job_id=%s launch_status=%s command=%s",
                session_id,
                session_id,
                entity.candidate_id,
                entity.job_id,
                response.launch_status,
                response.launch_command,
            )
        else:
            logger.info(
                "ai_interview.ten.command_ready trace_id=%s session_id=%s candidate_id=%s job_id=%s launch_status=%s command=<empty>",
                session_id,
                session_id,
                entity.candidate_id,
                entity.job_id,
                response.launch_status,
            )
        return response

    def launch_ten_session(self, session_id: str) -> AIInterviewTENRuntimeResponse:
        entity = self._session_repository.get(session_id)
        self._ensure_session_active_for_realtime(entity, action="ten_launch")
        ten_patch = self._prepare_ten_runtime(entity)
        if ten_patch:
            entity = self._session_repository.update_status(session_id, status=entity.status, payload_patch=ten_patch)
        property_file = str((entity.payload or {}).get("ten_property_file") or "")
        launch_patch = self._ten_runtime_manager.launch_session(session_id=session_id, property_file=property_file)
        entity = self._session_repository.update_status(session_id, status=entity.status, payload_patch=launch_patch)
        response = AIInterviewTENRuntimeResponse.model_validate(self._build_ten_runtime_response(entity))
        logger.info(
            "ai_interview.ten.launch trace_id=%s session_id=%s candidate_id=%s job_id=%s launch_status=%s command=%s",
            session_id,
            session_id,
            entity.candidate_id,
            entity.job_id,
            response.launch_status,
            response.launch_command or "",
        )
        return response

    def rtc_reconnect(self, session_id: str, payload: AIInterviewRTCReconnectRequest) -> AIInterviewRTCReconnectResponse:
        """Cleaned docstring."""
        entity = self._session_repository.get(session_id)
        self._ensure_session_active_for_realtime(entity, action="rtc_reconnect")
        merged = dict(entity.payload or {})
        reconnect_count = int(merged.get("rtc_reconnect_count", 0)) + 1
        reconnect_info = self._rtc_gateway.reconnect_room(
            session_id=session_id,
            room_id=entity.rtc_room_id,
            reconnect_count=reconnect_count,
            client_id=payload.client_id,
            reason=payload.reason,
        )
        self._session_repository.update_status(
            session_id,
            status=entity.status,
            payload_patch={"rtc_reconnect_count": reconnect_count, "rtc_last_reason": payload.reason, "rtc_client_id": payload.client_id},
        )
        self._event_repository.create(
            event_type="ai_interview.rtc.reconnect",
            entity_type="ai_interview_session",
            entity_id=session_id,
            status="success",
            operator="candidate",
            session_id=session_id,
            job_id=entity.job_id,
            payload={"client_id": payload.client_id, "reason": payload.reason, "reconnect_count": reconnect_count},
        )
        return AIInterviewRTCReconnectResponse(
            session_id=session_id,
            room_id=reconnect_info.room_id,
            reconnected=reconnect_info.reconnected,
            reconnect_count=reconnect_info.reconnect_count,
        )

    @staticmethod
    def _ensure_session_active_for_realtime(entity, *, action: str) -> None:
        if entity.status not in {InterviewSessionStatus.CREATED, InterviewSessionStatus.IN_PROGRESS}:
            raise InvalidStateError(
                f"AI interview session '{entity.id}' cannot perform '{action}' from status '{entity.status}'. "
                "Please create a new session for a new interview."
            )

    def rtc_subscribe_audio(self, session_id: str, payload: AIInterviewRTCAudioSubscribeRequest) -> AIInterviewRTCAudioSubscribeResponse:
        """Cleaned docstring."""
        entity = self._session_repository.get(session_id)
        if payload.candidate_id != entity.candidate_id:
            raise InvalidStateError("candidate_id 与会话不匹配")

        feature_enabled = bool(self._settings.ai_interview_rtc_audio_subscribe_enabled)
        participant_identity = (payload.participant_identity or f"{payload.candidate_id}:{payload.client_id}").strip()
        subscriber_identity = (payload.subscriber_identity or self._settings.ai_interview_rtc_audio_subscriber_identity or "ai-bot").strip()
        configured_track_sids = self._parse_track_sids_from_settings()
        track_sids = list(payload.track_sids or configured_track_sids)
        auto_subscribe = (
            payload.auto_subscribe
            if payload.auto_subscribe is not None
            else bool(self._settings.ai_interview_rtc_audio_subscribe_auto)
        )

        if not feature_enabled:
            self._event_repository.create(
                event_type="ai_interview.rtc.audio_subscribe",
                entity_type="ai_interview_session",
                entity_id=session_id,
                status="skipped",
                operator="system",
                session_id=session_id,
                job_id=entity.job_id,
                payload={"reason": "feature_disabled", "participant_identity": participant_identity, "subscriber_identity": subscriber_identity},
            )
            return AIInterviewRTCAudioSubscribeResponse(
                session_id=session_id,
                room_id=entity.rtc_room_id,
                participant_identity=participant_identity,
                subscriber_identity=subscriber_identity,
                subscribed=False,
                mode="disabled",
                track_sids=[],
                feature_enabled=False,
            )

        subscribe_info = self._rtc_gateway.subscribe_audio_tracks(
            session_id=session_id,
            room_id=entity.rtc_room_id,
            participant_identity=participant_identity,
            subscriber_identity=subscriber_identity,
            track_sids=track_sids,
            auto_subscribe=auto_subscribe,
        )
        self._session_repository.update_status(
            session_id,
            status=entity.status,
            payload_patch={
                "rtc_audio_subscribe_enabled": True,
                "rtc_audio_participant_identity": subscribe_info.participant_identity,
                "rtc_audio_subscriber_identity": subscribe_info.subscriber_identity,
                "rtc_audio_track_sids": subscribe_info.track_sids,
                "rtc_audio_subscribed": subscribe_info.subscribed,
                "rtc_audio_subscribe_mode": subscribe_info.mode,
            },
        )
        self._event_repository.create(
            event_type="ai_interview.rtc.audio_subscribe",
            entity_type="ai_interview_session",
            entity_id=session_id,
            status="success",
            operator="system",
            session_id=session_id,
            job_id=entity.job_id,
            payload={
                "participant_identity": subscribe_info.participant_identity,
                "subscriber_identity": subscribe_info.subscriber_identity,
                "track_sids": subscribe_info.track_sids,
                "mode": subscribe_info.mode,
                "auto_subscribe": auto_subscribe,
            },
        )
        return AIInterviewRTCAudioSubscribeResponse(
            session_id=session_id,
            room_id=subscribe_info.room_id,
            participant_identity=subscribe_info.participant_identity,
            subscriber_identity=subscribe_info.subscriber_identity,
            subscribed=subscribe_info.subscribed,
            mode=subscribe_info.mode,
            track_sids=subscribe_info.track_sids,
            feature_enabled=True,
        )

    def rtc_apply_video_policy(self, session_id: str, payload: AIInterviewRTCVideoPolicyRequest) -> AIInterviewRTCVideoPolicyResponse:
        """Cleaned docstring."""
        entity = self._session_repository.get(session_id)
        if payload.candidate_id != entity.candidate_id:
            raise InvalidStateError("candidate_id 与会话不匹配")

        feature_enabled = bool(self._settings.ai_interview_rtc_video_policy_enabled)
        participant_identity = (payload.participant_identity or f"{payload.candidate_id}:{payload.client_id}").strip()
        subscriber_identity = (payload.subscriber_identity or self._settings.ai_interview_rtc_video_subscriber_identity or "ai-bot").strip()
        configured_track_sids = self._parse_video_track_sids_from_settings()
        track_sids = list(payload.track_sids or configured_track_sids)
        auto_subscribe = (
            payload.auto_subscribe
            if payload.auto_subscribe is not None
            else bool(self._settings.ai_interview_rtc_video_subscribe_auto)
        )
        record_enabled = (
            payload.record_enabled
            if payload.record_enabled is not None
            else bool(self._settings.ai_interview_rtc_video_record_enabled)
        )

        if not feature_enabled:
            self._event_repository.create(
                event_type="ai_interview.rtc.video_policy",
                entity_type="ai_interview_session",
                entity_id=session_id,
                status="skipped",
                operator="system",
                session_id=session_id,
                job_id=entity.job_id,
                payload={"reason": "feature_disabled", "participant_identity": participant_identity, "subscriber_identity": subscriber_identity},
            )
            return AIInterviewRTCVideoPolicyResponse(
                session_id=session_id,
                room_id=entity.rtc_room_id,
                participant_identity=participant_identity,
                subscriber_identity=subscriber_identity,
                applied=False,
                subscribed=False,
                recording_enabled=record_enabled,
                mode="disabled",
                track_sids=[],
                feature_enabled=False,
            )

        policy_info = self._rtc_gateway.apply_video_policy(
            session_id=session_id,
            room_id=entity.rtc_room_id,
            participant_identity=participant_identity,
            subscriber_identity=subscriber_identity,
            track_sids=track_sids,
            auto_subscribe=auto_subscribe,
            record_enabled=record_enabled,
        )
        self._session_repository.update_status(
            session_id,
            status=entity.status,
            payload_patch={
                "rtc_video_policy_applied": policy_info.applied,
                "rtc_video_participant_identity": policy_info.participant_identity,
                "rtc_video_subscriber_identity": policy_info.subscriber_identity,
                "rtc_video_track_sids": policy_info.track_sids,
                "rtc_video_subscribed": policy_info.subscribed,
                "rtc_video_record_enabled": policy_info.recording_enabled,
                "rtc_video_policy_mode": policy_info.mode,
            },
        )
        self._event_repository.create(
            event_type="ai_interview.rtc.video_policy",
            entity_type="ai_interview_session",
            entity_id=session_id,
            status="success",
            operator="system",
            session_id=session_id,
            job_id=entity.job_id,
            payload={
                "participant_identity": policy_info.participant_identity,
                "subscriber_identity": policy_info.subscriber_identity,
                "track_sids": policy_info.track_sids,
                "subscribed": policy_info.subscribed,
                "recording_enabled": policy_info.recording_enabled,
                "mode": policy_info.mode,
                "auto_subscribe": auto_subscribe,
            },
        )
        return AIInterviewRTCVideoPolicyResponse(
            session_id=session_id,
            room_id=policy_info.room_id,
            participant_identity=policy_info.participant_identity,
            subscriber_identity=policy_info.subscriber_identity,
            applied=policy_info.applied,
            subscribed=policy_info.subscribed,
            recording_enabled=policy_info.recording_enabled,
            mode=policy_info.mode,
            track_sids=policy_info.track_sids,
            feature_enabled=True,
        )


