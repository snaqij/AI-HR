from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

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
            "title": "ASR Streaming Engineer",
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
                    "name": "ASR Candidate",
                    "source_channel": "boss",
                    "external_candidate_id": "cand-asr-stream-1",
                    "resume_text": "Python, streaming ASR",
                    "raw_profile": {"skills": ["Python", "ASR"]},
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


def test_asr_stream_chunked_should_write_partial_and_final_turns(api_client: TestClient) -> None:
    job_id = _create_job(api_client)
    candidate_id = _create_candidate(api_client)
    session_id = _create_ai_session(api_client, job_id, candidate_id)

    part_resp = api_client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/rtc/asr/stream",
        json={
            "seq": 1,
            "text_hint": "I led",
            "audio_base64": "UklGRg==",
            "chunk_index": 1,
            "chunk_total": 2,
            "is_final": False,
            "target_latency_ms": 700,
            "latency_ms": 320,
        },
    )
    assert part_resp.status_code == 200
    part_payload = part_resp.json()["data"]
    assert part_payload["is_partial"] is True
    assert part_payload["is_final"] is False
    assert part_payload["deduplicated"] is False
    assert part_payload["turn_id"] is not None
    assert part_payload["realtime_target_met"] is True
    assert part_payload["event_id"] == "asr-1-1"

    final_resp = api_client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/rtc/asr/stream",
        json={
            "seq": 1,
            "text_hint": "I led distributed reliability improvements",
            "audio_base64": "UklGRg==",
            "chunk_index": 2,
            "chunk_total": 2,
            "is_final": True,
            "target_latency_ms": 700,
            "latency_ms": 410,
        },
    )
    assert final_resp.status_code == 200
    final_payload = final_resp.json()["data"]
    assert final_payload["is_partial"] is False
    assert final_payload["is_final"] is True
    assert final_payload["deduplicated"] is False
    assert final_payload["turn_id"] is not None
    assert final_payload["event_id"] == "asr-1-2"

    replay_resp = api_client.get(f"/api/v1/ai/interviews/sessions/{session_id}/replay", params={"limit": 20, "offset": 0})
    assert replay_resp.status_code == 200
    items = replay_resp.json()["data"]["items"]
    speakers = [item["speaker"] for item in items]
    assert "candidate_partial" in speakers
    assert "candidate" in speakers

    audit_resp = api_client.get(
        "/api/v1/audit/events",
        params={"session_id": session_id, "event_type": "ai_interview.rtc.asr", "limit": 20},
    )
    assert audit_resp.status_code == 200
    audit_items = audit_resp.json()["data"]["items"]
    assert len(audit_items) >= 2
    assert any(item["payload"].get("chunk_index") == 1 for item in audit_items)
    assert any(item["payload"].get("chunk_index") == 2 for item in audit_items)


def test_asr_stream_should_fail_realtime_target_when_latency_too_high(api_client: TestClient) -> None:
    job_id = _create_job(api_client)
    candidate_id = _create_candidate(api_client)
    session_id = _create_ai_session(api_client, job_id, candidate_id)

    resp = api_client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/rtc/asr/stream",
        json={
            "seq": 9,
            "text_hint": "high latency sample",
            "audio_base64": "UklGRg==",
            "target_latency_ms": 300,
            "latency_ms": 450,
        },
    )
    assert resp.status_code == 200
    payload = resp.json()["data"]
    assert payload["p95_target_met"] is False
    assert payload["realtime_target_met"] is False
    assert payload["target_latency_ms"] == 300


def test_asr_stream_should_deduplicate_by_chunk_id(api_client: TestClient) -> None:
    job_id = _create_job(api_client)
    candidate_id = _create_candidate(api_client)
    session_id = _create_ai_session(api_client, job_id, candidate_id)

    first = api_client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/rtc/asr/stream",
        json={
            "seq": 3,
            "chunk_id": "chunk-fixed-1",
            "chunk_index": 1,
            "chunk_total": 1,
            "text_hint": "first",
            "audio_base64": "UklGRg==",
            "latency_ms": 220,
        },
    )
    assert first.status_code == 200
    assert first.json()["data"]["deduplicated"] is False

    second = api_client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/rtc/asr/stream",
        json={
            "seq": 3,
            "chunk_id": "chunk-fixed-1",
            "chunk_index": 1,
            "chunk_total": 1,
            "text_hint": "first",
            "audio_base64": "UklGRg==",
            "latency_ms": 220,
        },
    )
    assert second.status_code == 200
    payload = second.json()["data"]
    assert payload["deduplicated"] is True
    assert payload["turn_id"] is None


def test_asr_stream_should_reject_invalid_chunk_window(api_client: TestClient) -> None:
    job_id = _create_job(api_client)
    candidate_id = _create_candidate(api_client)
    session_id = _create_ai_session(api_client, job_id, candidate_id)

    resp = api_client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/rtc/asr/stream",
        json={
            "seq": 10,
            "chunk_index": 2,
            "chunk_total": 1,
            "text_hint": "invalid chunk window",
            "latency_ms": 200,
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "domain_error"
