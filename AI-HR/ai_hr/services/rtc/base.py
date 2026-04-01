"""RTC gateway abstractions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class RTCSessionInfo:
    """RTC session provisioning result."""

    room_id: str
    join_token: str
    vendor: str
    transport: str = "webrtc"
    app_id: str | None = None
    channel_name: str | None = None
    uid: str | None = None
    expire_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RTCReconnectInfo:
    """RTC reconnect result."""

    room_id: str
    reconnect_count: int
    reconnected: bool


@dataclass(frozen=True, slots=True)
class RTCAudioSubscriptionInfo:
    """RTC audio subscription result."""

    room_id: str
    participant_identity: str
    subscriber_identity: str
    subscribed: bool
    track_sids: list[str]
    mode: str = "auto"


@dataclass(frozen=True, slots=True)
class RTCBotAudioPublishInfo:
    """RTC bot audio publish result."""

    room_id: str
    bot_identity: str
    published: bool
    track_sid: str | None
    mode: str


@dataclass(frozen=True, slots=True)
class RTCVideoPolicyInfo:
    """RTC video policy result."""

    room_id: str
    participant_identity: str
    subscriber_identity: str
    applied: bool
    subscribed: bool
    recording_enabled: bool
    track_sids: list[str]
    mode: str


class RTCGateway:
    """RTC gateway contract."""

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
