from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_hr.core.config import get_settings
from ai_hr.db.base import Base
from ai_hr.db.models import AIInterviewSession
from ai_hr.db.session import get_db_session
from ai_hr.main import app

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
Base.metadata.create_all(bind=engine)


def override_get_db_session():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def api_client() -> TestClient:
    previous = app.dependency_overrides.get(get_db_session)
    app.dependency_overrides[get_db_session] = override_get_db_session
    client = TestClient(app)
    try:
        yield client
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db_session, None)
        else:
            app.dependency_overrides[get_db_session] = previous


def _create_job(client: TestClient) -> str:
    resp = client.post(
        "/api/v1/jobs",
        json={
            "title": "RTC Webhook Engineer",
            "department": "Engineering",
            "city": "Shanghai",
            "salary_range": "30k-45k",
            "requirements": "Python FastAPI LiveKit",
        },
    )
    assert resp.status_code == 201
    return resp.json()["data"]["id"]


def _create_candidate(client: TestClient) -> str:
    resp = client.post(
        "/api/v1/candidates/import",
        json={
            "candidates": [
                {
                    "name": "Webhook Candidate",
                    "source_channel": "boss",
                    "external_candidate_id": "cand-rtc-webhook-1",
                    "resume_text": "Python, livekit webhook",
                    "raw_profile": {"skills": ["Python", "LiveKit"]},
                }
            ]
        },
    )
    assert resp.status_code == 201
    return resp.json()["data"]["candidates"][0]["id"]


def _create_ai_session(client: TestClient, *, job_id: str, candidate_id: str) -> tuple[str, str]:
    resp = client.post(
        "/api/v1/ai/interviews/sessions",
        json={
            "candidate_id": candidate_id,
            "job_id": job_id,
        },
    )
    assert resp.status_code == 201
    session = resp.json()["data"]["session"]
    return session["id"], session["rtc_room_id"]


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def _build_livekit_token(*, api_key: str, api_secret: str, now_ts: int | None = None) -> str:
    now = int(now_ts or time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"iss": api_key, "nbf": now - 5, "exp": now + 120}
    header_segment = _b64url(json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    payload_segment = _b64url(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    signing_input = f"{header_segment}.{payload_segment}".encode("utf-8")
    signature = hmac.new(api_secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_segment}.{payload_segment}.{_b64url(signature)}"


def test_livekit_webhook_should_writeback_and_deduplicate(api_client: TestClient) -> None:
    job_id = _create_job(api_client)
    candidate_id = _create_candidate(api_client)
    session_id, room_id = _create_ai_session(api_client, job_id=job_id, candidate_id=candidate_id)

    settings = get_settings()
    old_enabled = settings.ai_interview_rtc_webhook_enabled
    old_sign_required = settings.livekit_webhook_signature_required
    old_audio_subscribe = settings.ai_interview_rtc_audio_subscribe_enabled
    try:
        settings.ai_interview_rtc_webhook_enabled = True
        settings.livekit_webhook_signature_required = False
        settings.ai_interview_rtc_audio_subscribe_enabled = False
        payload = {
            "id": "evt-join-1",
            "event": "participant_joined",
            "room": {"name": room_id},
            "participant": {"identity": "candidate-1:web"},
        }
        first = api_client.post("/api/v1/ai/interviews/rtc/webhooks/livekit", json=payload)
        assert first.status_code == 200
        first_data = first.json()["data"]
        assert first_data["accepted"] is True
        assert first_data["deduplicated"] is False
        assert first_data["session_id"] == session_id

        track_resp = api_client.post(
            "/api/v1/ai/interviews/rtc/webhooks/livekit",
            json={
                "id": "evt-track-1",
                "event": "track_published",
                "room": {"name": room_id},
                "participant": {"identity": "candidate-1:web"},
                "track": {"sid": "TR_AUDIO_1", "type": "audio"},
            },
        )
        assert track_resp.status_code == 200
        assert track_resp.json()["data"]["accepted"] is True

        second = api_client.post("/api/v1/ai/interviews/rtc/webhooks/livekit", json=payload)
        assert second.status_code == 200
        second_data = second.json()["data"]
        assert second_data["accepted"] is True
        assert second_data["deduplicated"] is True

        db = TestingSessionLocal()
        try:
            entity = db.get(AIInterviewSession, session_id)
            assert entity is not None
            payload_data = dict(entity.payload or {})
            assert payload_data.get("rtc_last_webhook_event_type") == "track_published"
            assert "candidate-1:web" in list(payload_data.get("rtc_participants", []))
            assert "evt-join-1" in list(payload_data.get("rtc_webhook_seen_event_ids", []))
            assert "TR_AUDIO_1" in list(payload_data.get("rtc_audio_track_sids", []))
        finally:
            db.close()
    finally:
        settings.ai_interview_rtc_webhook_enabled = old_enabled
        settings.livekit_webhook_signature_required = old_sign_required
        settings.ai_interview_rtc_audio_subscribe_enabled = old_audio_subscribe


def test_livekit_webhook_should_reject_invalid_signature_when_required(api_client: TestClient) -> None:
    settings = get_settings()
    old_enabled = settings.ai_interview_rtc_webhook_enabled
    old_sign_required = settings.livekit_webhook_signature_required
    old_secret = settings.livekit_api_secret
    old_webhook_key = settings.livekit_webhook_api_key
    try:
        settings.ai_interview_rtc_webhook_enabled = True
        settings.livekit_webhook_signature_required = True
        settings.livekit_api_secret = "livekit-secret-test"
        settings.livekit_webhook_api_key = "livekit-key-test"
        payload = {"id": "evt-auth-1", "event": "room_started", "room": {"name": "room-x"}}

        unauthorized = api_client.post("/api/v1/ai/interviews/rtc/webhooks/livekit", json=payload)
        assert unauthorized.status_code == 401

        bad_token = _build_livekit_token(api_key="livekit-key-test", api_secret="wrong-secret")
        denied = api_client.post(
            "/api/v1/ai/interviews/rtc/webhooks/livekit",
            headers={"Authorization": f"Bearer {bad_token}"},
            json=payload,
        )
        assert denied.status_code == 401

        good_token = _build_livekit_token(api_key="livekit-key-test", api_secret="livekit-secret-test")
        accepted = api_client.post(
            "/api/v1/ai/interviews/rtc/webhooks/livekit",
            headers={"Authorization": f"Bearer {good_token}"},
            json=payload,
        )
        assert accepted.status_code == 200
    finally:
        settings.ai_interview_rtc_webhook_enabled = old_enabled
        settings.livekit_webhook_signature_required = old_sign_required
        settings.livekit_api_secret = old_secret
        settings.livekit_webhook_api_key = old_webhook_key


def test_livekit_webhook_should_reject_invalid_json_payload(api_client: TestClient) -> None:
    settings = get_settings()
    old_enabled = settings.ai_interview_rtc_webhook_enabled
    old_sign_required = settings.livekit_webhook_signature_required
    try:
        settings.ai_interview_rtc_webhook_enabled = True
        settings.livekit_webhook_signature_required = False
        resp = api_client.post(
            "/api/v1/ai/interviews/rtc/webhooks/livekit",
            data="not-a-json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400
        assert resp.json().get("detail") == "invalid_webhook_payload"
    finally:
        settings.ai_interview_rtc_webhook_enabled = old_enabled
        settings.livekit_webhook_signature_required = old_sign_required
