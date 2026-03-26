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

