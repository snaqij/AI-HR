"""LiveKit RTC 网关实现。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass

from ...core.exceptions import ConnectorOperationError, InvalidConnectorConfigError
from .base import RTCAudioSubscriptionInfo, RTCBotAudioPublishInfo, RTCGateway, RTCReconnectInfo, RTCSessionInfo, RTCVideoPolicyInfo


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


@dataclass(frozen=True, slots=True)
class LiveKitConfig:
    base_url: str
    api_key: str
    api_secret: str
    create_room_path: str
    update_subscriptions_path: str
    send_data_path: str
    room_prefix: str
    token_ttl_seconds: int
    timeout_seconds: float = 5.0


class LiveKitRTCGateway(RTCGateway):
    """基于 LiveKit Server API 的 RTC 网关。"""

    provider_name = "livekit"

    def __init__(self, config: LiveKitConfig):
        self._cfg = config
        if not self._cfg.base_url or not self._cfg.api_key or not self._cfg.api_secret:
            raise InvalidConnectorConfigError("LiveKit config is incomplete")

    def create_room(self, *, session_id: str, preferred_room_id: str | None = None) -> RTCSessionInfo:
        room_id = preferred_room_id or f"{self._cfg.room_prefix}{uuid.uuid4()}"
        self._create_room_if_needed(room_id)
        join_token = self._build_access_token(identity=f"candidate-{session_id}", room=room_id)
        return RTCSessionInfo(room_id=room_id, join_token=join_token, vendor=self.provider_name)

    def join_room(self, *, session_id: str, room_id: str, client_id: str, candidate_id: str, join_token: str) -> RTCSessionInfo:
        token = join_token or self._build_access_token(identity=f"{candidate_id}:{client_id}", room=room_id)
        return RTCSessionInfo(room_id=room_id, join_token=token, vendor=self.provider_name)

    def reconnect_room(
        self,
        *,
        session_id: str,
        room_id: str,
        reconnect_count: int,
        client_id: str,
        reason: str,
    ) -> RTCReconnectInfo:
        # LiveKit 重连主要由 SDK 处理，这里做服务端可观测确认。
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
        if subscribed_track_sids:
            self._update_subscriptions(
                room_id=room_id,
                participant_identity=participant_identity,
                track_sids=subscribed_track_sids,
                subscribe=True,
            )
            return RTCAudioSubscriptionInfo(
                room_id=room_id,
                participant_identity=participant_identity,
                subscriber_identity=subscriber_identity,
                subscribed=True,
                track_sids=subscribed_track_sids,
                mode="server_api",
            )

        return RTCAudioSubscriptionInfo(
            room_id=room_id,
            participant_identity=participant_identity,
            subscriber_identity=subscriber_identity,
            subscribed=auto_subscribe,
            track_sids=[],
            mode="token_auto" if auto_subscribe else "disabled",
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
        if not audio_uris:
            return RTCBotAudioPublishInfo(
                room_id=room_id,
                bot_identity=bot_identity,
                published=False,
                track_sid=None,
                mode="empty_audio",
            )
        payload = {
            "session_id": session_id,
            "type": "tts_audio",
            "bot_identity": bot_identity,
            "track_name": track_name,
            "audio_uris": audio_uris,
            "chunks": chunks,
        }
        # Broadcast synthesized speech metadata to all room participants.
        self._send_data_to_room(room_id=room_id, payload=payload)
        short_hash = hashlib.sha1(f"{session_id}:{track_name}:{len(audio_uris)}".encode("utf-8")).hexdigest()[:12]
        return RTCBotAudioPublishInfo(
            room_id=room_id,
            bot_identity=bot_identity,
            published=True,
            track_sid=f"lk-bot-track-{short_hash}",
            mode="server_send_data_broadcast",
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
        subscribed = False
        mode = "token_auto" if auto_subscribe else "disabled"
        if resolved_track_sids:
            self._update_subscriptions(
                room_id=room_id,
                participant_identity=participant_identity,
                track_sids=resolved_track_sids,
                subscribe=True,
            )
            subscribed = True
            mode = "server_api"
        else:
            subscribed = auto_subscribe

        self._send_data_to_participant(
            room_id=room_id,
            participant_identity=subscriber_identity,
            payload={
                "session_id": session_id,
                "type": "video_policy",
                "record_enabled": record_enabled,
                "auto_subscribe": auto_subscribe,
                "track_sids": resolved_track_sids,
            },
        )
        return RTCVideoPolicyInfo(
            room_id=room_id,
            participant_identity=participant_identity,
            subscriber_identity=subscriber_identity,
            applied=True,
            subscribed=subscribed,
            recording_enabled=record_enabled,
            track_sids=resolved_track_sids,
            mode=mode,
        )

    def _build_access_token(self, *, identity: str, room: str, room_admin: bool = False) -> str:
        now = int(time.time())
        video_grants = {
            "room": room,
            "roomJoin": True,
            "canPublish": True,
            "canSubscribe": True,
        }
        if room_admin:
            # Server-side control API calls require room administration grants.
            video_grants["roomCreate"] = True
            video_grants["roomAdmin"] = True
        payload = {
            "iss": self._cfg.api_key,
            "sub": identity,
            "nbf": now - 5,
            "exp": now + max(60, self._cfg.token_ttl_seconds),
            "video": video_grants,
        }
        header = {"alg": "HS256", "typ": "JWT"}
        header_segment = _b64url(json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        payload_segment = _b64url(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        signing_input = f"{header_segment}.{payload_segment}".encode("utf-8")
        signature = hmac.new(self._cfg.api_secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        return f"{header_segment}.{payload_segment}.{_b64url(signature)}"

    def _create_room_if_needed(self, room_id: str) -> None:
        url = f"{self._cfg.base_url.rstrip('/')}{self._cfg.create_room_path}"
        payload = {"name": room_id, "emptyTimeout": 300, "maxParticipants": 4}
        token = self._build_access_token(identity="server", room=room_id, room_admin=True)
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url=url,
            method="POST",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._cfg.timeout_seconds) as response:
                status_code = int(getattr(response, "status", 200))
                if status_code >= 400:
                    raise ConnectorOperationError(f"LiveKit create room failed: status={status_code}")
        except urllib.error.HTTPError as exc:
            # 409 表示房间已存在，可视为幂等成功。
            if exc.code == 409:
                return
            raise ConnectorOperationError(f"LiveKit create room HTTP error: {exc.code}") from exc
        except Exception as exc:  # pragma: no cover
            raise ConnectorOperationError(f"LiveKit create room error: {exc}") from exc

    def _update_subscriptions(self, *, room_id: str, participant_identity: str, track_sids: list[str], subscribe: bool) -> None:
        url = f"{self._cfg.base_url.rstrip('/')}{self._cfg.update_subscriptions_path}"
        payload = {
            "room": room_id,
            "identity": participant_identity,
            "trackSids": track_sids,
            "subscribe": subscribe,
        }
        token = self._build_access_token(identity="server", room=room_id, room_admin=True)
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url=url,
            method="POST",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._cfg.timeout_seconds) as response:
                status_code = int(getattr(response, "status", 200))
                if status_code >= 400:
                    raise ConnectorOperationError(f"LiveKit update subscriptions failed: status={status_code}")
        except urllib.error.HTTPError as exc:
            raise ConnectorOperationError(f"LiveKit update subscriptions HTTP error: {exc.code}") from exc
        except Exception as exc:  # pragma: no cover
            raise ConnectorOperationError(f"LiveKit update subscriptions error: {exc}") from exc

    def _send_data_to_participant(self, *, room_id: str, participant_identity: str, payload: dict) -> None:
        self._send_data(room_id=room_id, payload=payload, destination_identities=[participant_identity])

    def _send_data_to_room(self, *, room_id: str, payload: dict) -> None:
        self._send_data(room_id=room_id, payload=payload, destination_identities=None)

    def _send_data(self, *, room_id: str, payload: dict, destination_identities: list[str] | None) -> None:
        url = f"{self._cfg.base_url.rstrip('/')}{self._cfg.send_data_path}"
        body_payload = {
            "room": room_id,
            "data": _b64url(json.dumps(payload, ensure_ascii=False).encode("utf-8")),
            "kind": 1,
            "topic": "ai_hr.tts.inject",
        }
        if destination_identities:
            body_payload["destinationIdentities"] = [item for item in destination_identities if str(item).strip()]
        token = self._build_access_token(identity="server", room=room_id, room_admin=True)
        body = json.dumps(body_payload).encode("utf-8")
        request = urllib.request.Request(
            url=url,
            method="POST",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._cfg.timeout_seconds) as response:
                status_code = int(getattr(response, "status", 200))
                if status_code >= 400:
                    raise ConnectorOperationError(f"LiveKit send data failed: status={status_code}")
        except urllib.error.HTTPError as exc:
            raise ConnectorOperationError(f"LiveKit send data HTTP error: {exc.code}") from exc
        except Exception as exc:  # pragma: no cover
            raise ConnectorOperationError(f"LiveKit send data error: {exc}") from exc
