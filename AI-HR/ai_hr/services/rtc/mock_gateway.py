"""Mock RTC 网关实现。"""

from __future__ import annotations

import uuid
from hashlib import sha1

from .base import RTCAudioSubscriptionInfo, RTCBotAudioPublishInfo, RTCGateway, RTCReconnectInfo, RTCSessionInfo, RTCVideoPolicyInfo


class MockRTCGateway(RTCGateway):
    """用于离线测试环境的 RTC 模拟实现。"""

    provider_name = "mock"

    def create_room(self, *, session_id: str, preferred_room_id: str | None = None) -> RTCSessionInfo:
        room_id = preferred_room_id or f"ai-intv-{uuid.uuid4()}"
        join_token = uuid.uuid4().hex
        return RTCSessionInfo(room_id=room_id, join_token=join_token, vendor=self.provider_name)

    def join_room(self, *, session_id: str, room_id: str, client_id: str, candidate_id: str, join_token: str) -> RTCSessionInfo:
        return RTCSessionInfo(room_id=room_id, join_token=join_token, vendor=self.provider_name)

    def reconnect_room(
        self,
        *,
        session_id: str,
        room_id: str,
        reconnect_count: int,
        client_id: str,
        reason: str,
    ) -> RTCReconnectInfo:
        return RTCReconnectInfo(room_id=room_id, reconnect_count=reconnect_count, reconnected=True)

    def subscribe_audio_tracks(
        self,
        *,
        session_id: str,
        room_id: str,
        participant_identity: str,
        subscriber_identity: str,
        track_sids: list[str],
        auto_subscribe: bool,
    ) -> RTCAudioSubscriptionInfo:
        subscribed_track_sids = list(track_sids)
        if auto_subscribe and not subscribed_track_sids:
            subscribed_track_sids = [f"mock-audio-{session_id}"]
        return RTCAudioSubscriptionInfo(
            room_id=room_id,
            participant_identity=participant_identity,
            subscriber_identity=subscriber_identity,
            subscribed=auto_subscribe or bool(subscribed_track_sids),
            track_sids=subscribed_track_sids,
            mode="mock_auto" if auto_subscribe else "mock_manual",
        )

    def publish_bot_audio(
        self,
        *,
        session_id: str,
        room_id: str,
        bot_identity: str,
        track_name: str,
        audio_uris: list[str],
        chunks: list[str],
    ) -> RTCBotAudioPublishInfo:
        signature = sha1(f"{session_id}:{track_name}:{len(audio_uris)}:{len(chunks)}".encode("utf-8")).hexdigest()[:12]
        return RTCBotAudioPublishInfo(
            room_id=room_id,
            bot_identity=bot_identity,
            published=bool(audio_uris),
            track_sid=f"mock-bot-track-{signature}" if audio_uris else None,
            mode="mock_track",
        )

    def apply_video_policy(
        self,
        *,
        session_id: str,
        room_id: str,
        participant_identity: str,
        subscriber_identity: str,
        track_sids: list[str],
        auto_subscribe: bool,
        record_enabled: bool,
    ) -> RTCVideoPolicyInfo:
        resolved_track_sids = list(track_sids)
        if auto_subscribe and not resolved_track_sids:
            resolved_track_sids = [f"mock-video-{session_id}"]
        return RTCVideoPolicyInfo(
            room_id=room_id,
            participant_identity=participant_identity,
            subscriber_identity=subscriber_identity,
            applied=True,
            subscribed=auto_subscribe or bool(resolved_track_sids),
            recording_enabled=record_enabled,
            track_sids=resolved_track_sids,
            mode="mock_video_auto" if auto_subscribe else "mock_video_manual",
        )
