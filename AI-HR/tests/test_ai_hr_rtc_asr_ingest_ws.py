from __future__ import annotations

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


def _create_job(client: TestClient) -> str:
    resp = client.post(
        "/api/v1/jobs",
        json={
            "title": "RTC Ingest WS Engineer",
            "department": "Engineering",
            "city": "Shanghai",
            "salary_range": "30k-45k",
            "requirements": "Python FastAPI WebSocket",
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
                    "name": "RTC Ingest WS Candidate",
                    "source_channel": "boss",
                    "external_candidate_id": "cand-rtc-ingest-ws-1",
                    "resume_text": "Python, websocket ingest",
                    "raw_profile": {"skills": ["Python", "WebSocket"]},
                }
            ]
        },
    )
    assert resp.status_code == 201
    return resp.json()["data"]["candidates"][0]["id"]


def _create_started_session(client: TestClient, *, job_id: str, candidate_id: str) -> tuple[str, str]:
    resp = client.post(
        "/api/v1/ai/interviews/sessions",
        json={"candidate_id": candidate_id, "job_id": job_id},
    )
    assert resp.status_code == 201
    session_data = resp.json()["data"]["session"]
    session_id = session_data["id"]
    room_id = session_data["rtc_room_id"]
    started = client.post(f"/api/v1/ai/interviews/sessions/{session_id}/start", json={"operator": "ingest_ws_test"})
    assert started.status_code == 200
    return session_id, room_id


def test_rtc_asr_ingest_ws_should_ack_and_return_result() -> None:
    previous = app.dependency_overrides.get(get_db_session)
    app.dependency_overrides[get_db_session] = override_get_db_session
    client = TestClient(app)
    try:
        job_id = _create_job(client)
        candidate_id = _create_candidate(client)
        _, room_id = _create_started_session(client, job_id=job_id, candidate_id=candidate_id)

        with client.websocket_connect("/api/v1/ai/interviews/rtc/asr/ingest/ws") as ws:
            connected = ws.receive_json()
            assert connected["type"] == "ingest.connected"

            ws.send_json(
                {
                    "type": "audio_frame",
                    "payload": {
                        "room_id": room_id,
                        "seq": 1,
                        "frame_id": "ingest-ws-frame-1",
                        "text_hint": "ok",
                        "audio_base64": "UklGRg==",
                        "input_format": "wav",
                        "chunk_index": 1,
                        "chunk_total": 1,
                        "is_final": True,
                        "auto_followup": True,
                        "auto_tts_publish": False,
                    },
                }
            )
            ack = ws.receive_json()
            assert ack["type"] == "ingest.ack"
            assert ack["status"] == "accepted"
            assert ack["frame_id"] == "ingest-ws-frame-1"
            assert int(ack.get("ack_latency_ms") or 0) >= 1

            result = ws.receive_json()
            assert result["type"] == "ingest.result"
            data = result["data"]
            assert data["room_id"] == room_id
            assert data["asr"]["seq"] == 1
            assert data["asr"]["deduplicated"] is False
            assert data["event"] is not None
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db_session, None)
        else:
            app.dependency_overrides[get_db_session] = previous
        client.close()


def test_rtc_asr_ingest_ws_should_deduplicate_frame_id() -> None:
    previous = app.dependency_overrides.get(get_db_session)
    app.dependency_overrides[get_db_session] = override_get_db_session
    client = TestClient(app)
    try:
        job_id = _create_job(client)
        candidate_id = _create_candidate(client)
        _, room_id = _create_started_session(client, job_id=job_id, candidate_id=candidate_id)

        payload = {
            "type": "audio_frame",
            "payload": {
                "room_id": room_id,
                "seq": 2,
                "frame_id": "ingest-ws-dup-1",
                "text_hint": "ok",
                "audio_base64": "UklGRg==",
                "input_format": "wav",
                "chunk_index": 1,
                "chunk_total": 1,
                "is_final": True,
            },
        }
        with client.websocket_connect("/api/v1/ai/interviews/rtc/asr/ingest/ws") as ws:
            _ = ws.receive_json()
            ws.send_json(payload)
            first_ack = ws.receive_json()
            assert first_ack["type"] == "ingest.ack"
            assert first_ack["status"] == "accepted"
            _ = ws.receive_json()

            ws.send_json(payload)
            second_ack = ws.receive_json()
            assert second_ack["type"] == "ingest.ack"
            assert second_ack["status"] == "duplicate"
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db_session, None)
        else:
            app.dependency_overrides[get_db_session] = previous
        client.close()


def test_rtc_asr_ingest_ws_should_return_validation_error() -> None:
    previous = app.dependency_overrides.get(get_db_session)
    app.dependency_overrides[get_db_session] = override_get_db_session
    client = TestClient(app)
    try:
        with client.websocket_connect("/api/v1/ai/interviews/rtc/asr/ingest/ws") as ws:
            _ = ws.receive_json()
            ws.send_json({"type": "audio_frame", "payload": {"seq": 1}})
            error = ws.receive_json()
            assert error["type"] == "ingest.error"
            assert error["error"] == "validation_error"
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db_session, None)
        else:
            app.dependency_overrides[get_db_session] = previous
        client.close()
