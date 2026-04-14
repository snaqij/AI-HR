from __future__ import annotations

import os

os.environ["AI_HR_BOSS_MODE"] = "mock"
os.environ["AI_HR_ENV_FILE"] = ""

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_hr.db.base import Base
from ai_hr.db.models import CandidateResumeAccessRetry
from ai_hr.db.session import get_db_session
from ai_hr.main import app
from ai_hr.services.ai_resume import get_ai_resume_service


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


@pytest.fixture(autouse=True)
def reset_db_override():
    app.dependency_overrides[get_db_session] = override_get_db_session
    yield
    app.dependency_overrides[get_db_session] = override_get_db_session


def test_parse_resume_persists_structured_profile() -> None:
    import_response = client.post(
        "/api/v1/candidates/import",
        json={
            "candidates": [
                {
                    "name": "Alice",
                    "source_channel": "boss",
                    "external_candidate_id": "cand-ai-parse-1",
                    "resume_text": "5年Python开发经验，本科，做过支付项目，熟悉FastAPI与MySQL。",
                    "raw_profile": {"skills": ["Python", "FastAPI"], "job_hops": 2},
                }
            ]
        },
    )
    candidate_id = import_response.json()["data"]["candidates"][0]["id"]

    parse_response = client.post(
        "/api/v1/ai/resume/parse",
        json={"candidate_id": candidate_id},
    )
    assert parse_response.status_code == 200
    payload = parse_response.json()["data"]["profile"]
    assert payload["candidate_id"] == candidate_id
    assert payload["parse_status"] == "parsed"
    assert payload["confidence"] >= 0.5
    assert "skills" in payload["parsed_profile"]
    assert "python" in payload["normalized_profile"]["skills"]

    get_response = client.get(f"/api/v1/candidates/{candidate_id}/resume-profile")
    assert get_response.status_code == 200
    get_payload = get_response.json()["data"]["profile"]
    assert get_payload["candidate_id"] == candidate_id
    assert get_payload["parser_version"] == "heuristic-v1"


def test_normalize_resume_updates_profile_status() -> None:
    import_response = client.post(
        "/api/v1/candidates/import",
        json={
            "candidates": [
                {
                    "name": "Bob",
                    "source_channel": "boss",
                    "external_candidate_id": "cand-ai-norm-1",
                    "resume_text": "3 years Java and Python engineer, bachelor degree.",
                    "raw_profile": {"skills": ["Python3", "Java"]},
                }
            ]
        },
    )
    candidate_id = import_response.json()["data"]["candidates"][0]["id"]

    parse_response = client.post("/api/v1/ai/resume/parse", json={"candidate_id": candidate_id})
    assert parse_response.status_code == 200

    normalize_response = client.post("/api/v1/ai/resume/normalize", json={"candidate_id": candidate_id})
    assert normalize_response.status_code == 200
    payload = normalize_response.json()["data"]["profile"]
    assert payload["parse_status"] == "normalized"
    assert payload["normalized_profile"]["education_level"] == "本科"
    assert "python" in payload["normalized_profile"]["skills"]


def test_parse_resume_without_text_returns_domain_error() -> None:
    import_response = client.post(
        "/api/v1/candidates/import",
        json={
            "candidates": [
                {
                    "name": "NoText",
                    "source_channel": "boss",
                    "external_candidate_id": "cand-ai-empty-1",
                    "raw_profile": {},
                }
            ]
        },
    )
    candidate_id = import_response.json()["data"]["candidates"][0]["id"]

    parse_response = client.post("/api/v1/ai/resume/parse", json={"candidate_id": candidate_id})
    assert parse_response.status_code == 400
    payload = parse_response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "domain_error"


def test_get_missing_resume_profile_returns_404() -> None:
    import_response = client.post(
        "/api/v1/candidates/import",
        json={
            "candidates": [
                {
                    "name": "NoProfile",
                    "source_channel": "boss",
                    "external_candidate_id": "cand-ai-missing-profile-1",
                    "resume_text": "仅导入未解析",
                    "raw_profile": {},
                }
            ]
        },
    )
    candidate_id = import_response.json()["data"]["candidates"][0]["id"]

    response = client.get(f"/api/v1/candidates/{candidate_id}/resume-profile")
    assert response.status_code == 404
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "not_found"


def test_sync_resume_attachment_persists_binary_and_updates_candidate() -> None:
    import_response = client.post(
        "/api/v1/candidates/import",
        json={
            "candidates": [
                {
                    "name": "AttachmentUser",
                    "source_channel": "boss",
                    "external_candidate_id": "cand-attachment-1",
                    "raw_profile": {"uid": 123, "jobId": 456},
                }
            ]
        },
    )
    candidate = import_response.json()["data"]["candidates"][0]
    candidate_id = candidate["id"]

    sync_response = client.post(f"/api/v1/candidates/{candidate_id}/resume-attachment/sync")
    assert sync_response.status_code == 200
    payload = sync_response.json()["data"]
    assert payload["attachment"]["candidate_id"] == candidate_id
    assert payload["attachment"]["file_name"] == "mock-resume.pdf"
    assert payload["attachment"]["file_size_bytes"] > 0

    second_sync = client.post(f"/api/v1/candidates/{candidate_id}/resume-attachment/sync")
    assert second_sync.status_code == 200
    second_payload = second_sync.json()["data"]
    assert second_payload["attachment"]["file_sha256"] == payload["attachment"]["file_sha256"]


def test_sync_resume_access_requests_and_downloads_attachment() -> None:
    import_response = client.post(
        "/api/v1/candidates/import",
        json={
            "candidates": [
                {
                    "name": "ResumeAccessUser",
                    "source_channel": "boss",
                    "external_candidate_id": "cand-access-1",
                    "raw_profile": {"uid": 123, "jobId": 456},
                }
            ]
        },
    )
    candidate_id = import_response.json()["data"]["candidates"][0]["id"]

    sync_response = client.post(f"/api/v1/candidates/{candidate_id}/resume-access/sync")
    assert sync_response.status_code == 200
    payload = sync_response.json()["data"]
    assert payload["candidate_id"] == candidate_id
    assert payload["request_status"] == 0
    assert payload["resume_visible"] is True
    assert payload["attachment_synced"] is True
    assert payload["attachment"]["file_name"] == "mock-resume.pdf"


def test_resume_access_creates_retry_and_retry_worker_downloads_when_visible_later() -> None:
    import_response = client.post(
        "/api/v1/candidates/import",
        json={
            "candidates": [
                {
                    "name": "RetryResumeUser",
                    "source_channel": "boss",
                    "external_candidate_id": "cand-access-retry-1",
                    "raw_profile": {
                        "uid": 123,
                        "jobId": 456,
                        "mock_resume_visible_after_request": False,
                        "mock_resume_retry_visible": True,
                    },
                }
            ]
        },
    )
    candidate_id = import_response.json()["data"]["candidates"][0]["id"]

    sync_response = client.post(f"/api/v1/candidates/{candidate_id}/resume-access/sync")
    assert sync_response.status_code == 200
    payload = sync_response.json()["data"]
    assert payload["resume_visible"] is False
    assert payload["attachment_synced"] is False

    with TestingSessionLocal() as session:
        retry_row = session.execute(select(CandidateResumeAccessRetry)).scalar_one()
        retry_row.next_retry_at = retry_row.created_at
        session.commit()
        results = get_ai_resume_service(session).execute_due_resume_access_retries(limit=5)
        assert len(results) == 1
        assert results[0]["status"] == "downloaded"

    with TestingSessionLocal() as session:
        retry_row = session.execute(select(CandidateResumeAccessRetry)).scalar_one()
        assert retry_row.attachment_downloaded is True
        assert retry_row.status == "downloaded"


def test_sync_job_resume_attachments_batches_all_candidates_under_job() -> None:
    create_response = client.post(
        "/api/v1/jobs",
        json={
            "title": "Resume Batch Sync Engineer",
            "department": "Engineering",
            "city": "Shanghai",
            "salary_range": "30k-45k",
            "requirements": "Python, FastAPI, MySQL",
        },
    )
    job_id = create_response.json()["data"]["id"]

    publish_response = client.post(
        f"/api/v1/jobs/{job_id}/publish",
        json={"channels": ["boss"]},
    )
    assert publish_response.status_code == 200

    first_sync = client.post(
        f"/api/v1/jobs/{job_id}/candidates/sync",
        json={"channels": ["boss"], "max_pages": 1},
    )
    assert first_sync.status_code == 200

    second_sync = client.post(
        f"/api/v1/jobs/{job_id}/candidates/sync",
        json={"channels": ["boss"], "max_pages": 1},
    )
    assert second_sync.status_code == 200

    batch_sync = client.post(
        f"/api/v1/jobs/{job_id}/resume-attachments/sync",
        json={},
    )
    assert batch_sync.status_code == 200
    payload = batch_sync.json()["data"]
    assert payload["job_id"] == job_id
    assert payload["total_candidates"] == 2
    assert payload["succeeded_count"] == 2
    assert payload["failed_count"] == 0
    assert all(item["status"] == "synced" for item in payload["results"])
    assert all(item["attachment"]["file_name"] == "mock-resume.pdf" for item in payload["results"])


def test_sync_job_resume_access_batches_all_candidates_under_job() -> None:
    create_response = client.post(
        "/api/v1/jobs",
        json={
            "title": "Resume Access Engineer",
            "department": "Engineering",
            "city": "Shanghai",
            "salary_range": "30k-45k",
            "requirements": "Python, FastAPI, MySQL",
        },
    )
    job_id = create_response.json()["data"]["id"]

    client.post(
        f"/api/v1/jobs/{job_id}/publish",
        json={"channels": ["boss"]},
    )
    client.post(
        f"/api/v1/jobs/{job_id}/candidates/sync",
        json={"channels": ["boss"], "max_pages": 2},
    )

    batch_sync = client.post(
        f"/api/v1/jobs/{job_id}/resume-access/sync",
        json={},
    )
    assert batch_sync.status_code == 200
    payload = batch_sync.json()["data"]
    assert payload["job_id"] == job_id
    assert payload["total_candidates"] == 2
    assert payload["succeeded_count"] == 2
    assert all(item["resume_visible"] is True for item in payload["results"])
    assert all(item["attachment_synced"] is True for item in payload["results"])
