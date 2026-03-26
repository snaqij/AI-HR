from __future__ import annotations

import base64
import json

from ai_hr.services.rtc.livekit_gateway import LiveKitConfig, LiveKitRTCGateway
from ai_hr.services.rtc.mock_gateway import MockRTCGateway


def _build_livekit_gateway() -> LiveKitRTCGateway:
    return LiveKitRTCGateway(
        LiveKitConfig(
            base_url="https://livekit.example.com",
            api_key="test_key",
            api_secret="test_secret",
            create_room_path="/twirp/livekit.RoomService/CreateRoom",
            update_subscriptions_path="/twirp/livekit.RoomService/UpdateSubscriptions",
            send_data_path="/twirp/livekit.RoomService/SendData",
            room_prefix="ai-intv-",
            token_ttl_seconds=600,
            timeout_seconds=3.0,
        )
    )


def test_mock_gateway_audio_subscribe_auto_should_return_mock_track() -> None:
    gateway = MockRTCGateway()
    result = gateway.subscribe_audio_tracks(
        session_id="sess-1",
        room_id="room-1",
        participant_identity="candidate-1:web",
        subscriber_identity="ai-bot",
        track_sids=[],
        auto_subscribe=True,
    )

    assert result.subscribed is True
    assert result.mode == "mock_auto"
    assert len(result.track_sids) == 1


def test_livekit_gateway_audio_subscribe_should_call_server_api_when_track_sids_provided() -> None:
    gateway = _build_livekit_gateway()
    captured: dict[str, object] = {}

    def _capture_update(*, room_id: str, participant_identity: str, track_sids: list[str], subscribe: bool) -> None:
        captured["room_id"] = room_id
        captured["participant_identity"] = participant_identity
        captured["track_sids"] = track_sids
        captured["subscribe"] = subscribe

    gateway._update_subscriptions = _capture_update  # type: ignore[method-assign]

    result = gateway.subscribe_audio_tracks(
        session_id="sess-2",
        room_id="room-2",
        participant_identity="candidate-2:web",
        subscriber_identity="ai-bot",
        track_sids=["TR_A", "TR_B"],
        auto_subscribe=True,
    )

    assert result.subscribed is True
    assert result.mode == "server_api"
    assert result.track_sids == ["TR_A", "TR_B"]
    assert captured == {
        "room_id": "room-2",
        "participant_identity": "candidate-2:web",
        "track_sids": ["TR_A", "TR_B"],
        "subscribe": True,
    }


def test_livekit_gateway_audio_subscribe_should_fallback_to_token_auto_without_track_sids() -> None:
    gateway = _build_livekit_gateway()
    result = gateway.subscribe_audio_tracks(
        session_id="sess-3",
        room_id="room-3",
        participant_identity="candidate-3:web",
        subscriber_identity="ai-bot",
        track_sids=[],
        auto_subscribe=True,
    )

    assert result.subscribed is True
    assert result.mode == "token_auto"
    assert result.track_sids == []


def test_livekit_gateway_server_token_should_include_room_admin_grants() -> None:
    gateway = _build_livekit_gateway()
    token = gateway._build_access_token(identity="server", room="room-admin-1", room_admin=True)  # type: ignore[attr-defined]
    payload_b64 = token.split(".")[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(payload_b64.encode("utf-8")).decode("utf-8"))
    video = payload["video"]
    assert video["room"] == "room-admin-1"
    assert video["roomCreate"] is True
    assert video["roomAdmin"] is True


def test_livekit_gateway_publish_bot_audio_should_call_send_data() -> None:
    gateway = _build_livekit_gateway()
    captured: dict[str, object] = {}

    def _capture_send(*, room_id: str, payload: dict, destination_identities: list[str] | None) -> None:
        captured["room_id"] = room_id
        captured["destination_identities"] = destination_identities
        captured["payload"] = payload

    gateway._send_data = _capture_send  # type: ignore[method-assign]

    result = gateway.publish_bot_audio(
        session_id="sess-tts-1",
        room_id="room-tts-1",
        bot_identity="ai-bot",
        track_name="ai-bot-tts",
        audio_uris=["data:audio/mpeg;base64,abc"],
        chunks=["hello"],
    )

    assert result.published is True
    assert result.mode == "server_send_data_broadcast"
    assert isinstance(result.track_sid, str) and result.track_sid.startswith("lk-bot-track-")
    assert captured["room_id"] == "room-tts-1"
    assert captured["destination_identities"] is None


def test_mock_gateway_apply_video_policy_should_return_recording_flags() -> None:
    gateway = MockRTCGateway()
    result = gateway.apply_video_policy(
        session_id="sess-v1",
        room_id="room-v1",
        participant_identity="candidate-v:web",
        subscriber_identity="ai-bot",
        track_sids=[],
        auto_subscribe=True,
        record_enabled=True,
    )
    assert result.applied is True
    assert result.subscribed is True
    assert result.recording_enabled is True
    assert result.mode == "mock_video_auto"


def test_livekit_gateway_apply_video_policy_should_call_update_and_send_data() -> None:
    gateway = _build_livekit_gateway()
    calls: dict[str, object] = {}

    def _capture_update(*, room_id: str, participant_identity: str, track_sids: list[str], subscribe: bool) -> None:
        calls["update_room_id"] = room_id
        calls["update_identity"] = participant_identity
        calls["update_track_sids"] = track_sids
        calls["update_subscribe"] = subscribe

    def _capture_send(*, room_id: str, participant_identity: str, payload: dict) -> None:
        calls["send_room_id"] = room_id
        calls["send_identity"] = participant_identity
        calls["send_payload"] = payload

    gateway._update_subscriptions = _capture_update  # type: ignore[method-assign]
    gateway._send_data_to_participant = _capture_send  # type: ignore[method-assign]

    result = gateway.apply_video_policy(
        session_id="sess-v2",
        room_id="room-v2",
        participant_identity="candidate-v2:web",
        subscriber_identity="ai-bot",
        track_sids=["TR_VIDEO_1"],
        auto_subscribe=True,
        record_enabled=True,
    )
    assert result.applied is True
    assert result.subscribed is True
    assert result.recording_enabled is True
    assert result.mode == "server_api"
    assert calls["update_room_id"] == "room-v2"
    assert calls["send_identity"] == "ai-bot"
