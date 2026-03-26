"""RTC 网关抽象。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RTCSessionInfo:
    """RTC 会话基础信息。"""

    room_id: str
    join_token: str
    vendor: str
    transport: str = "webrtc"


@dataclass(frozen=True, slots=True)
class RTCReconnectInfo:
    """RTC 重连结果。"""

    room_id: str
    reconnect_count: int
    reconnected: bool


@dataclass(frozen=True, slots=True)
class RTCAudioSubscriptionInfo:
    """RTC 音轨订阅结果。"""

    room_id: str
    participant_identity: str
    subscriber_identity: str
    subscribed: bool
    track_sids: list[str]
    mode: str = "auto"


@dataclass(frozen=True, slots=True)
class RTCBotAudioPublishInfo:
    """RTC AI bot 音频回灌结果。"""

    room_id: str
    bot_identity: str
    published: bool
    track_sid: str | None
    mode: str


@dataclass(frozen=True, slots=True)
class RTCVideoPolicyInfo:
    """RTC 视频策略应用结果。"""

    room_id: str
    participant_identity: str
    subscriber_identity: str
    applied: bool
    subscribed: bool
    recording_enabled: bool
    track_sids: list[str]
    mode: str


class RTCGateway:
    """RTC 网关能力约束。"""

    provider_name: str = "unknown"

    def create_room(self, *, session_id: str, preferred_room_id: str | None = None) -> RTCSessionInfo:
        raise NotImplementedError

    def join_room(self, *, session_id: str, room_id: str, client_id: str, candidate_id: str, join_token: str) -> RTCSessionInfo:
        raise NotImplementedError

    def reconnect_room(
        self,
        *,
        session_id: str,
        room_id: str,
        reconnect_count: int,
        client_id: str,
        reason: str,
    ) -> RTCReconnectInfo:
        raise NotImplementedError

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
        raise NotImplementedError

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
        raise NotImplementedError

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
        raise NotImplementedError
