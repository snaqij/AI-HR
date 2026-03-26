from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_hr.core.config import get_settings
from ai_hr.core.exceptions import AIHRException
from ai_hr.db.base import Base
from ai_hr.db.session import get_db_session
from ai_hr.main import create_app


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


def _build_client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db_session] = override_get_db_session
    return TestClient(app)


def _create_job_and_candidate(client: TestClient) -> tuple[str, str]:
    job_resp = client.post(
        "/api/v1/jobs",
        json={
            "title": "Security Test Backend Engineer",
            "department": "Engineering",
            "city": "Shanghai",
            "salary_range": "30k-45k",
            "requirements": "Python FastAPI",
        },
    )
    assert job_resp.status_code == 201
    job_id = job_resp.json()["data"]["id"]

    cand_resp = client.post(
        "/api/v1/candidates/import",
        json={
            "candidates": [
                {
                    "name": "Security Candidate",
                    "source_channel": "boss",
                    "external_candidate_id": "cand-security-1",
                    "resume_text": "Python and FastAPI experience",
                    "raw_profile": {"skills": ["Python", "FastAPI"]},
                }
            ]
        },
    )
    assert cand_resp.status_code == 201
    candidate_id = cand_resp.json()["data"]["candidates"][0]["id"]
    return job_id, candidate_id


def test_request_trace_header_should_be_injected_and_propagated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_HR_ENVIRONMENT", "dev")
    monkeypatch.setenv("AI_HR_CORS_ALLOW_ORIGINS", "http://localhost:5173")
    get_settings.cache_clear()
    client = _build_client()

    health_resp = client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.headers.get("x-trace-id")

    fixed_trace = "trace-fixed-001"
    forwarded = client.get("/health", headers={"x-trace-id": fixed_trace})
    assert forwarded.status_code == 200
    assert forwarded.headers.get("x-trace-id") == fixed_trace

    get_settings.cache_clear()


def test_create_app_should_reject_wildcard_cors_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_HR_ENVIRONMENT", "production")
    monkeypatch.setenv("AI_HR_CORS_ALLOW_ORIGINS", "*")
    get_settings.cache_clear()
    with pytest.raises(AIHRException, match="Wildcard CORS origin is forbidden in production"):
        create_app()
    get_settings.cache_clear()


def test_ai_interview_auth_should_require_api_key_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_HR_ENVIRONMENT", "production")
    monkeypatch.setenv("AI_HR_CORS_ALLOW_ORIGINS", "https://hr.example.com")
    monkeypatch.setenv("AI_HR_AI_INTERVIEW_API_KEYS", "k-prod-1")
    monkeypatch.setenv("AI_HR_AI_INTERVIEW_AUTH_REQUIRED", "true")
    get_settings.cache_clear()
    client = _build_client()
    job_id, candidate_id = _create_job_and_candidate(client)

    denied = client.post(
        "/api/v1/ai/interviews/sessions",
        json={"candidate_id": candidate_id, "job_id": job_id},
    )
    assert denied.status_code == 401

    allowed = client.post(
        "/api/v1/ai/interviews/sessions",
        headers={"x-api-key": "k-prod-1"},
        json={"candidate_id": candidate_id, "job_id": job_id},
    )
    assert allowed.status_code == 201
    assert allowed.json()["ok"] is True
    get_settings.cache_clear()

