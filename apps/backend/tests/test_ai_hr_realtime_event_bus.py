from __future__ import annotations

import os
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
from ai_hr.services.orchestrator.event_bus import DEFAULT_INTERVIEW_EVENT_BUS, InterviewEventBus, _build_default_event_bus

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
            "title": "Realtime WS Engineer",
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
                    "name": "Realtime Candidate",
                    "source_channel": "boss",
                    "external_candidate_id": "cand-realtime-ws-1",
                    "resume_text": "Python, websocket",
                    "raw_profile": {"skills": ["Python", "WebSocket"]},
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


def test_realtime_ws_should_receive_bus_event() -> None:
    previous = app.dependency_overrides.get(get_db_session)
    app.dependency_overrides[get_db_session] = override_get_db_session
    client = TestClient(app)
    try:
        job_id = _create_job(client)
        candidate_id = _create_candidate(client)
        session_id = _create_ai_session(client, job_id, candidate_id)

        with client.websocket_connect(f"/api/v1/ai/interviews/sessions/{session_id}/events/ws") as ws:
            connected = ws.receive_json()
            assert connected["event_type"] == "connected"
            DEFAULT_INTERVIEW_EVENT_BUS.publish(
                session_id=session_id,
                event_type="asr.turn",
                payload={"speaker": "candidate", "is_final": True, "transcript": "hello"},
            )
            event = ws.receive_json()
            assert event["event_type"] == "asr.turn"
            payload = event["payload"]
            assert payload["speaker"] == "candidate"
            assert payload["is_final"] is True
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db_session, None)
        else:
            app.dependency_overrides[get_db_session] = previous
        client.close()


def test_redis_event_bus_should_drop_to_memory_when_redis_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_HR_AI_INTERVIEW_REDIS_ENABLED", "true")
    monkeypatch.setenv("AI_HR_AI_INTERVIEW_REDIS_EVENT_BUS_ENABLED", "true")
    monkeypatch.setenv("AI_HR_REDIS_URL", "redis://127.0.0.1:6399/15")
    get_settings.cache_clear()
    bus = _build_default_event_bus()
    assert isinstance(bus, InterviewEventBus)
    get_settings.cache_clear()


def test_redis_event_bus_should_publish_and_receive_cross_instance() -> None:
    redis_url = os.getenv("AI_HR_TEST_REDIS_URL")
    if not redis_url:
        pytest.skip("AI_HR_TEST_REDIS_URL not set")
    from ai_hr.services.orchestrator.event_bus_redis import RedisInterviewEventBus

    bus_a = RedisInterviewEventBus(redis_url=redis_url, redis_prefix="aihr-test")
    bus_b = RedisInterviewEventBus(redis_url=redis_url, redis_prefix="aihr-test")
    loop = __import__("asyncio").new_event_loop()
    try:
        bus_b.bind_loop(loop)
        sub = bus_b.subscribe(session_id="s-cross")
        bus_a.publish(session_id="s-cross", event_type="llm.delta", payload={"delta": "hello"})
        deadline = time.time() + 2
        received = None
        while time.time() < deadline:
            if not sub.queue.empty():
                received = sub.queue.get_nowait()
                break
            time.sleep(0.05)
        assert received is not None
        assert received["event_type"] == "llm.delta"
    finally:
        loop.close()
