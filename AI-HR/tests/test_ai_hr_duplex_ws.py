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
            "title": "Duplex Engineer",
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
                    "name": "Duplex Candidate",
                    "source_channel": "boss",
                    "external_candidate_id": "cand-duplex-1",
                    "resume_text": "Python, realtime duplex",
                    "raw_profile": {"skills": ["Python", "Realtime"]},
                }
            ]
        },
    )
    assert resp.status_code == 201
    return resp.json()["data"]["candidates"][0]["id"]


def _create_started_session(client: TestClient, job_id: str, candidate_id: str) -> str:
    resp = client.post(
        "/api/v1/ai/interviews/sessions",
        json={"candidate_id": candidate_id, "job_id": job_id},
    )
    assert resp.status_code == 201
    session_id = resp.json()["data"]["session"]["id"]
    started = client.post(f"/api/v1/ai/interviews/sessions/{session_id}/start", json={"operator": "test"})
    assert started.status_code == 200
    return session_id


def test_duplex_ws_should_process_audio_chunk() -> None:
    previous = app.dependency_overrides.get(get_db_session)
    app.dependency_overrides[get_db_session] = override_get_db_session
    client = TestClient(app)
    try:
        job_id = _create_job(client)
        candidate_id = _create_candidate(client)
        session_id = _create_started_session(client, job_id, candidate_id)

        with client.websocket_connect(f"/api/v1/ai/interviews/sessions/{session_id}/rtc/duplex/ws") as ws:
            connected = ws.receive_json()
            assert connected["type"] == "duplex.connected"

            ws.send_json(
                {
                    "type": "audio_chunk",
                    "frame_id": "frame-1",
                    "seq": 1,
                    "audio_base64": "UklGRg==",
                    "chunk_index": 1,
                    "chunk_total": 1,
                    "is_final": True,
                    "input_format": "wav",
                }
            )
            ack = ws.receive_json()
            assert ack["type"] == "duplex.ack"
            assert ack["frame_id"] == "frame-1"
            assert ack["status"] == "accepted"
            assert int(ack.get("ack_latency_ms") or 0) >= 1
            turn = ws.receive_json()
            assert turn["type"] == "duplex.turn"
            data = turn["data"]
            assert data["asr"]["seq"] == 1
            assert data["asr"]["is_final"] is True
            assert data["event"] is not None
            assert isinstance(data["event"].get("followup_audio_uris"), list)
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db_session, None)
        else:
            app.dependency_overrides[get_db_session] = previous
        client.close()


def test_duplex_ws_should_deduplicate_frame_id() -> None:
    previous = app.dependency_overrides.get(get_db_session)
    app.dependency_overrides[get_db_session] = override_get_db_session
    client = TestClient(app)
    try:
        job_id = _create_job(client)
        candidate_id = _create_candidate(client)
        session_id = _create_started_session(client, job_id, candidate_id)

        payload = {
            "type": "audio_chunk",
            "frame_id": "dup-frame-1",
            "seq": 1,
            "audio_base64": "UklGRg==",
            "chunk_index": 1,
            "chunk_total": 1,
            "is_final": True,
            "input_format": "wav",
        }
        with client.websocket_connect(f"/api/v1/ai/interviews/sessions/{session_id}/rtc/duplex/ws") as ws:
            connected = ws.receive_json()
            assert connected["type"] == "duplex.connected"

            ws.send_json(payload)
            ack = ws.receive_json()
            assert ack["type"] == "duplex.ack"
            assert ack["frame_id"] == "dup-frame-1"
            assert ack["status"] == "accepted"
            assert int(ack.get("ack_latency_ms") or 0) >= 1
            turn = ws.receive_json()
            assert turn["type"] == "duplex.turn"

            ws.send_json(payload)
            duplicate = ws.receive_json()
            assert duplicate["type"] == "duplex.ack"
            assert duplicate["frame_id"] == "dup-frame-1"
            assert duplicate["status"] == "duplicate"
            assert int(duplicate.get("ack_latency_ms") or 0) >= 1
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db_session, None)
        else:
            app.dependency_overrides[get_db_session] = previous
        client.close()


def test_duplex_ws_should_accept_client_playback_mark() -> None:
    previous = app.dependency_overrides.get(get_db_session)
    app.dependency_overrides[get_db_session] = override_get_db_session
    client = TestClient(app)
    try:
        job_id = _create_job(client)
        candidate_id = _create_candidate(client)
        session_id = _create_started_session(client, job_id, candidate_id)

        with client.websocket_connect(f"/api/v1/ai/interviews/sessions/{session_id}/rtc/duplex/ws") as ws:
            connected = ws.receive_json()
            assert connected["type"] == "duplex.connected"

            ws.send_json(
                {
                    "type": "client_playback_mark",
                    "seq": 1,
                    "packet_index": 1,
                    "client_ts_ms": 1710000000000,
                    "transport": "binary",
                }
            )
            ack = ws.receive_json()
            assert ack["type"] == "duplex.client_playback_ack"
            assert ack["seq"] == 1
            assert ack["packet_index"] == 1
            assert ack["status"] == "accepted"
            assert int(ack.get("ack_latency_ms") or 0) >= 1
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db_session, None)
        else:
            app.dependency_overrides[get_db_session] = previous
        client.close()
