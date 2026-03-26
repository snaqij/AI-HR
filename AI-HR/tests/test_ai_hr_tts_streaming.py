from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_hr.core.config import get_settings
from ai_hr.db.base import Base
from ai_hr.db.session import get_db_session
from ai_hr.main import app
from ai_hr.services.speech.mock_providers import MockTTSProvider

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
            "title": "TTS Streaming Engineer",
            "department": "Engineering",
            "city": "Shanghai",
            "salary_range": "30k-45k",
            "requirements": "Python FastAPI",
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
                    "name": "TTS Candidate",
                    "source_channel": "boss",
                    "external_candidate_id": "cand-tts-stream-1",
                    "resume_text": "Python, streaming TTS",
                    "raw_profile": {"skills": ["Python", "TTS"]},
                }
            ]
        },
    )
    assert resp.status_code == 201
    return resp.json()["data"]["candidates"][0]["id"]


def _create_ai_session(client: TestClient, job_id: str, candidate_id: str) -> str:
    resp = client.post(
        "/api/v1/ai/interviews/sessions",
        json={
            "candidate_id": candidate_id,
            "job_id": job_id,
        },
    )
    assert resp.status_code == 201
    return resp.json()["data"]["session"]["id"]


def test_tts_stream_should_publish_to_bot_track_when_enabled(api_client: TestClient) -> None:
    job_id = _create_job(api_client)
    candidate_id = _create_candidate(api_client)
    session_id = _create_ai_session(api_client, job_id, candidate_id)

    settings = get_settings()
    old_enabled = settings.ai_interview_rtc_tts_publish_enabled
    old_bot = settings.ai_interview_rtc_tts_bot_identity
    try:
        settings.ai_interview_rtc_tts_publish_enabled = True
        settings.ai_interview_rtc_tts_bot_identity = "ai-bot"
        tts_resp = api_client.post(
            f"/api/v1/ai/interviews/sessions/{session_id}/rtc/tts/stream",
            json={
                "text": "Please describe your incident response process.",
                "voice": "female_a",
                "chunk_size": 10,
                "publish_to_rtc": True,
                "target_latency_ms": 1200,
            },
        )
    finally:
        settings.ai_interview_rtc_tts_publish_enabled = old_enabled
        settings.ai_interview_rtc_tts_bot_identity = old_bot

    assert tts_resp.status_code == 200
    payload = tts_resp.json()["data"]
    assert payload["published"] is True
    assert payload["publish_mode"] == "mock_track"
    assert payload["track_sid"].startswith("mock-bot-track-")
    assert payload["realtime_target_met"] is True
    assert payload["p95_target_met"] is True
    assert "tts_ms" in payload["latency_breakdown"]
    assert "publish_ms" in payload["latency_breakdown"]

    replay_resp = api_client.get(f"/api/v1/ai/interviews/sessions/{session_id}/replay", params={"limit": 20, "offset": 0})
    assert replay_resp.status_code == 200
    items = replay_resp.json()["data"]["items"]
    assert any(item["speaker"] == "ai" for item in items)

    audit_resp = api_client.get(
        "/api/v1/audit/events",
        params={"session_id": session_id, "event_type": "ai_interview.rtc.tts", "limit": 20},
    )
    assert audit_resp.status_code == 200
    audit_items = audit_resp.json()["data"]["items"]
    assert any(item["payload"].get("published") is True for item in audit_items)


def test_tts_stream_should_skip_publish_when_disabled(api_client: TestClient) -> None:
    job_id = _create_job(api_client)
    candidate_id = _create_candidate(api_client)
    session_id = _create_ai_session(api_client, job_id, candidate_id)

    settings = get_settings()
    old_enabled = settings.ai_interview_rtc_tts_publish_enabled
    try:
        settings.ai_interview_rtc_tts_publish_enabled = False
        tts_resp = api_client.post(
            f"/api/v1/ai/interviews/sessions/{session_id}/rtc/tts/stream",
            json={
                "text": "Please provide one measurable result.",
                "voice": "female_a",
                "chunk_size": 12,
            },
        )
    finally:
        settings.ai_interview_rtc_tts_publish_enabled = old_enabled

    assert tts_resp.status_code == 200
    payload = tts_resp.json()["data"]
    assert payload["published"] is False
    assert payload["publish_mode"] == "disabled"
    assert payload["track_sid"] is None


def test_tts_stream_should_fail_latency_target_when_tts_is_slow(api_client: TestClient) -> None:
    job_id = _create_job(api_client)
    candidate_id = _create_candidate(api_client)
    session_id = _create_ai_session(api_client, job_id, candidate_id)

    original = MockTTSProvider.synthesize_stream

    def _slow(self, *, session_id: str, text: str, voice: str, chunk_size: int):
        time.sleep(0.12)
        return original(self, session_id=session_id, text=text, voice=voice, chunk_size=chunk_size)

    MockTTSProvider.synthesize_stream = _slow  # type: ignore[assignment]
    try:
        tts_resp = api_client.post(
            f"/api/v1/ai/interviews/sessions/{session_id}/rtc/tts/stream",
            json={
                "text": "Describe one production outage you fixed.",
                "voice": "female_a",
                "chunk_size": 10,
                "target_latency_ms": 100,
            },
        )
    finally:
        MockTTSProvider.synthesize_stream = original  # type: ignore[assignment]

    assert tts_resp.status_code == 200
    payload = tts_resp.json()["data"]
    assert payload["realtime_target_met"] is False
    assert payload["p95_target_met"] is False
    assert payload["latency_breakdown"]["e2e_ms"] > 100
