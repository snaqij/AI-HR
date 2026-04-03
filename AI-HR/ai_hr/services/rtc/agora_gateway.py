"""Agora RTC gateway implementation."""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from ...core.exceptions import InvalidConnectorConfigError
from .base import RTCAudioSubscriptionInfo, RTCBotAudioPublishInfo, RTCGateway, RTCReconnectInfo, RTCSessionInfo, RTCVideoPolicyInfo

try:  # pragma: no cover - optional dependency
    from agora_token_builder import RtcTokenBuilder
except Exception:  # pragma: no cover - optional dependency
    RtcTokenBuilder = None


PUBLISHER_ROLE = 1


@dataclass(frozen=True, slots=True)
class AgoraConfig:
    app_id: str
    app_certificate: str | None
    room_prefix: str
    token_ttl_seconds: int
    ten_bot_user_id_prefix: str


class AgoraRTCGateway(RTCGateway):
    """Agora token + channel provisioning for AI interview sessions."""

    provider_name = "agora"

    def __init__(self, config: AgoraConfig):
        self._cfg = config
        if not self._cfg.app_id:
            raise InvalidConnectorConfigError("Agora provider requires app_id")
        if RtcTokenBuilder is None:
            raise InvalidConnectorConfigError("Agora provider requires dependency 'agora-token-builder'")

    def create_room(self, *, session_id: str, preferred_room_id: str | None = None) -> RTCSessionInfo:
        room_id = preferred_room_id or f"{self._cfg.room_prefix}{uuid.uuid4()}"
        candidate_uid = self._stable_uid(f"{session_id}:candidate:web")
        bot_uid = self._stable_uid(f"{session_id}:ten-bot")
        expire_at = self._expire_at()
        return RTCSessionInfo(
            room_id=room_id,
            join_token=self._build_token(room_id=room_id, uid=candidate_uid),
            vendor=self.provider_name,
            app_id=self._cfg.app_id,
            channel_name=room_id,
            uid=str(candidate_uid),
            expire_at=expire_at,
            metadata={
                "ten_bot_uid": str(bot_uid),
                "ten_bot_token": self._build_token(room_id=room_id, uid=bot_uid),
                "ten_bot_expire_at": expire_at.isoformat(),
            },
        )

    def join_room(self, *, session_id: str, room_id: str, client_id: str, candidate_id: str, join_token: str) -> RTCSessionInfo:
        uid = self._stable_uid(f"{candidate_id}:{client_id}")
        expire_at = self._expire_at()
        return RTCSessionInfo(
            room_id=room_id,
            join_token=self._build_token(room_id=room_id, uid=uid),
            vendor=self.provider_name,
            app_id=self._cfg.app_id,
            channel_name=room_id,
            uid=str(uid),
            expire_at=expire_at,
        )

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
        return RTCAudioSubscriptionInfo(
            room_id=room_id,
            participant_identity=participant_identity,
            subscriber_identity=subscriber_identity,
            subscribed=auto_subscribe or bool(track_sids),
            track_sids=list(track_sids),
            mode="agora_auto" if auto_subscribe else "agora_manual",
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
        track_sig = hashlib.sha1(f"{session_id}:{track_name}:{len(chunks)}".encode("utf-8")).hexdigest()[:12]
        return RTCBotAudioPublishInfo(
            room_id=room_id,
            bot_identity=bot_identity,
            published=bool(audio_uris or chunks),
            track_sid=f"agora-bot-track-{track_sig}" if (audio_uris or chunks) else None,
            mode="agora_sdk",
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
        return RTCVideoPolicyInfo(
            room_id=room_id,
            participant_identity=participant_identity,
            subscriber_identity=subscriber_identity,
            applied=True,
            subscribed=auto_subscribe or bool(track_sids),
            recording_enabled=record_enabled,
            track_sids=list(track_sids),
            mode="agora_client_policy",
        )

    def _build_token(self, *, room_id: str, uid: int) -> str:
        privilege_expired_ts = int(time.time()) + max(60, int(self._cfg.token_ttl_seconds))
        if not self._cfg.app_certificate:
            return ""
        return RtcTokenBuilder.buildTokenWithUid(
            self._cfg.app_id,
            self._cfg.app_certificate,
            room_id,
            uid,
            PUBLISHER_ROLE,
            privilege_expired_ts,
        )

    def _expire_at(self) -> datetime:
        return datetime.fromtimestamp(int(time.time()) + max(60, int(self._cfg.token_ttl_seconds)), tz=UTC)

    @staticmethod
    def _stable_uid(seed: str) -> int:
        # Keep uid within Agora uint32 range and avoid the reserved zero uid.
        return (int(hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8], 16) % 2147483646) + 1
