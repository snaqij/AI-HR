from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_hr.core.config import get_settings
from ai_hr.db.base import Base
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
            "title": "RTC Ingest Engineer",
            "department": "Engineering",
            "city": "Shanghai",
            "salary_range": "30k-45k",
            "requirements": "Python FastAPI ASR TTS",
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
                    "name": "RTC Ingest Candidate",
                    "source_channel": "boss",
                    "external_candidate_id": "cand-rtc-ingest-1",
                    "resume_text": "Python, realtime speech",
                    "raw_profile": {"skills": ["Python", "ASR", "TTS"]},
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
    session_id = session["id"]
    room_id = session["rtc_room_id"]
    started = client.post(f"/api/v1/ai/interviews/sessions/{session_id}/start", json={"operator": "rtc_ingest_test"})
    assert started.status_code == 200
    return session_id, room_id


def test_rtc_asr_ingest_should_chain_asr_event_and_tts(api_client: TestClient) -> None:
    job_id = _create_job(api_client)
    candidate_id = _create_candidate(api_client)
    session_id, room_id = _create_ai_session(api_client, job_id=job_id, candidate_id=candidate_id)

    settings = get_settings()
    old_publish_enabled = settings.ai_interview_rtc_tts_publish_enabled
    try:
        settings.ai_interview_rtc_tts_publish_enabled = True
        resp = api_client.post(
            "/api/v1/ai/interviews/rtc/asr/ingest",
            json={
                "room_id": room_id,
                "seq": 1,
                "frame_id": "frame-1",
                "text_hint": "ok",
                "audio_base64": "UklGRg==",
                "input_format": "wav",
                "chunk_index": 1,
                "chunk_total": 1,
                "is_final": True,
                "participant_identity": "candidate-1:web",
                "track_sid": "TR_AUDIO_1",
                "auto_followup": True,
                "auto_tts_publish": True,
            },
        )
    finally:
        settings.ai_interview_rtc_tts_publish_enabled = old_publish_enabled

    assert resp.status_code == 200
    payload = resp.json()["data"]
    assert payload["session_id"] == session_id
    assert payload["room_id"] == room_id
    assert payload["asr"]["deduplicated"] is False
    assert payload["asr"]["is_final"] is True
    assert payload["asr"]["turn_id"] is not None
    assert payload["event"] is not None
    assert payload["event"]["accepted"] is True
    assert bool(str(payload["event"]["followup_question"] or "").strip()) is True
    assert payload["tts"] is not None
    assert payload["tts"]["published"] is True
    assert str(payload["tts"]["track_sid"]).startswith("mock-bot-track-")

    audit_resp = api_client.get(
        "/api/v1/audit/events",
        params={"session_id": session_id, "event_type": "ai_interview.rtc.asr_ingest", "limit": 20},
    )
    assert audit_resp.status_code == 200
    items = audit_resp.json()["data"]["items"]
    assert any(item["payload"].get("asr_deduplicated") is False for item in items)


def test_rtc_asr_ingest_should_skip_followup_for_duplicate_frame(api_client: TestClient) -> None:
    job_id = _create_job(api_client)
    candidate_id = _create_candidate(api_client)
    _, room_id = _create_ai_session(api_client, job_id=job_id, candidate_id=candidate_id)

    payload = {
        "room_id": room_id,
        "seq": 2,
        "frame_id": "frame-dup-1",
        "text_hint": "This frame is duplicated.",
        "audio_base64": "UklGRg==",
        "input_format": "wav",
        "chunk_index": 1,
        "chunk_total": 1,
        "is_final": True,
        "auto_followup": True,
        "auto_tts_publish": True,
    }
    first = api_client.post("/api/v1/ai/interviews/rtc/asr/ingest", json=payload)
    assert first.status_code == 200
    assert first.json()["data"]["asr"]["deduplicated"] is False
    assert first.json()["data"]["event"] is not None

    second = api_client.post("/api/v1/ai/interviews/rtc/asr/ingest", json=payload)
    assert second.status_code == 200
    second_data = second.json()["data"]
    assert second_data["asr"]["deduplicated"] is True
    assert second_data["event"] is None
    assert second_data["tts"] is None


def test_rtc_asr_ingest_should_fail_when_room_not_found(api_client: TestClient) -> None:
    resp = api_client.post(
        "/api/v1/ai/interviews/rtc/asr/ingest",
        json={
            "room_id": "not-exists-room",
            "seq": 1,
            "frame_id": "frame-x",
            "audio_base64": "UklGRg==",
            "chunk_index": 1,
            "chunk_total": 1,
            "is_final": True,
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "domain_error"
