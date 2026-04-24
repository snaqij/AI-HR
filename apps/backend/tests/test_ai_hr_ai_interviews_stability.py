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


app.dependency_overrides[get_db_session] = override_get_db_session
client = TestClient(app)


def _create_job_candidate() -> tuple[str, str]:
    job_resp = client.post(
        "/api/v1/jobs",
        json={
            "title": "Stability Engineer",
            "department": "Engineering",
            "city": "Shanghai",
            "salary_range": "30k-45k",
            "requirements": "Python FastAPI",
        },
    )
    candidate_resp = client.post(
        "/api/v1/candidates/import",
        json={
            "candidates": [
                {
                    "name": "Stability Candidate",
                    "source_channel": "boss",
                    "external_candidate_id": "cand-stability-1",
                    "resume_text": "Python FastAPI",
                    "raw_profile": {"skills": ["Python", "FastAPI"]},
                }
            ]
        },
    )
    return job_resp.json()["data"]["id"], candidate_resp.json()["data"]["candidates"][0]["id"]


def test_stability_smoke_under_burst_events() -> None:
    """QA-006：轻量稳定性测试，验证突发事件写入与幂等不崩溃。"""
    job_id, candidate_id = _create_job_candidate()
    session_resp = client.post(
        "/api/v1/ai/interviews/sessions",
        json={"candidate_id": candidate_id, "job_id": job_id},
    )
    session_id = session_resp.json()["data"]["session"]["id"]
    assert client.post(f"/api/v1/ai/interviews/sessions/{session_id}/start", json={}).status_code == 200

    accepted = 0
    for idx in range(60):
        resp = client.post(
            f"/api/v1/ai/interviews/sessions/{session_id}/events",
            json={
                "event_id": f"evt-burst-{idx}",
                "speaker": "candidate",
                "transcript": f"burst-{idx}",
                "confidence": 0.86,
                "latency_ms": 800 + idx,
            },
        )
        assert resp.status_code == 200
        accepted += 1 if resp.json()["data"]["accepted"] else 0

    assert accepted == 60
    replay = client.get(f"/api/v1/ai/interviews/sessions/{session_id}/replay", params={"limit": 60})
    assert replay.status_code == 200
    assert replay.json()["data"]["total_turns"] >= 60
