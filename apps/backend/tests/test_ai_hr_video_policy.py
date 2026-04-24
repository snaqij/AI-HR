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
            "title": "Video Policy Engineer",
            "department": "Engineering",
            "city": "Shanghai",
            "salary_range": "30k-45k",
            "requirements": "WebRTC video",
        },
    )
    assert resp.status_code == 201
    return resp.json()["data"]["id"]


def _create_candidate(client: TestClient, suffix: str) -> str:
    resp = client.post(
        "/api/v1/candidates/import",
        json={
            "candidates": [
                {
                    "name": f"Video Candidate {suffix}",
                    "source_channel": "boss",
                    "external_candidate_id": f"cand-video-{suffix}",
                    "resume_text": "Video interview",
                    "raw_profile": {"skills": ["WebRTC", "Video"]},
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


def test_rtc_video_policy_should_apply_with_recording_enabled(api_client: TestClient) -> None:
    job_id = _create_job(api_client)
    candidate_id = _create_candidate(api_client, "001")
    session_id = _create_ai_session(api_client, job_id, candidate_id)

    settings = get_settings()
    old_enabled = settings.ai_interview_rtc_video_policy_enabled
    old_auto = settings.ai_interview_rtc_video_subscribe_auto
    old_record = settings.ai_interview_rtc_video_record_enabled
    old_identity = settings.ai_interview_rtc_video_subscriber_identity
    try:
        settings.ai_interview_rtc_video_policy_enabled = True
        settings.ai_interview_rtc_video_subscribe_auto = True
        settings.ai_interview_rtc_video_record_enabled = True
        settings.ai_interview_rtc_video_subscriber_identity = "ai-bot"

        resp = api_client.post(
            f"/api/v1/ai/interviews/sessions/{session_id}/rtc/video/policy",
            json={
                "candidate_id": candidate_id,
                "client_id": "web-video-1",
                "track_sids": ["TR_VIDEO_X"],
                "record_enabled": True,
            },
        )
    finally:
        settings.ai_interview_rtc_video_policy_enabled = old_enabled
        settings.ai_interview_rtc_video_subscribe_auto = old_auto
        settings.ai_interview_rtc_video_record_enabled = old_record
        settings.ai_interview_rtc_video_subscriber_identity = old_identity

    assert resp.status_code == 200
    payload = resp.json()["data"]
    assert payload["feature_enabled"] is True
    assert payload["applied"] is True
    assert payload["subscribed"] is True
    assert payload["recording_enabled"] is True
    assert payload["mode"] in {"mock_video_auto", "mock_video_manual", "server_api", "token_auto"}


def test_rtc_video_policy_should_skip_when_feature_disabled(api_client: TestClient) -> None:
    job_id = _create_job(api_client)
    candidate_id = _create_candidate(api_client, "002")
    session_id = _create_ai_session(api_client, job_id, candidate_id)

    settings = get_settings()
    old_enabled = settings.ai_interview_rtc_video_policy_enabled
    try:
        settings.ai_interview_rtc_video_policy_enabled = False
        resp = api_client.post(
            f"/api/v1/ai/interviews/sessions/{session_id}/rtc/video/policy",
            json={
                "candidate_id": candidate_id,
                "client_id": "web-video-2",
            },
        )
    finally:
        settings.ai_interview_rtc_video_policy_enabled = old_enabled

    assert resp.status_code == 200
    payload = resp.json()["data"]
    assert payload["feature_enabled"] is False
    assert payload["applied"] is False
    assert payload["mode"] == "disabled"


def test_metrics_should_include_video_policy_strategy_indicators(api_client: TestClient) -> None:
    job_id = _create_job(api_client)
    settings = get_settings()
    old_enabled = settings.ai_interview_rtc_video_policy_enabled
    old_record = settings.ai_interview_rtc_video_record_enabled
    try:
        settings.ai_interview_rtc_video_policy_enabled = True
        settings.ai_interview_rtc_video_record_enabled = True

        candidate_id = _create_candidate(api_client, "003")
        session_id = _create_ai_session(api_client, job_id, candidate_id)
        apply_resp = api_client.post(
            f"/api/v1/ai/interviews/sessions/{session_id}/rtc/video/policy",
            json={
                "candidate_id": candidate_id,
                "client_id": "web-video-3",
                "record_enabled": True,
            },
        )
        assert apply_resp.status_code == 200

        metric_resp = api_client.get("/api/v1/ai/interviews/metrics", params={"window_minutes": 120, "min_samples": 1})
    finally:
        settings.ai_interview_rtc_video_policy_enabled = old_enabled
        settings.ai_interview_rtc_video_record_enabled = old_record

    assert metric_resp.status_code == 200
    metrics = metric_resp.json()["data"]
    assert metrics["video_policy_applied_count"] >= 1
    assert metrics["video_policy_applied_rate"] > 0
    assert metrics["video_recording_enabled_count"] >= 1
    assert metrics["video_recording_enabled_rate"] > 0
