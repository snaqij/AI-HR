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


def _create_job() -> str:
    response = client.post(
        "/api/v1/jobs",
        json={
            "title": "Senior Backend Engineer",
            "department": "Engineering",
            "city": "Shanghai",
            "salary_range": "35k-50k",
            "requirements": "Python FastAPI MySQL Kubernetes",
        },
    )
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _import_candidates() -> list[str]:
    response = client.post(
        "/api/v1/candidates/import",
        json={
            "candidates": [
                {
                    "name": "Alice",
                    "source_channel": "boss",
                    "external_candidate_id": "cand-ai-score-1",
                    "resume_text": "6年Python开发经验，本科，擅长FastAPI和MySQL，负责过云平台项目。",
                    "raw_profile": {"skills": ["Python", "FastAPI", "MySQL"], "job_hops": 1},
                },
                {
                    "name": "Bob",
                    "source_channel": "boss",
                    "external_candidate_id": "cand-ai-score-2",
                    "resume_text": "2 years Java backend engineer, bachelor degree, knows Docker.",
                    "raw_profile": {"skills": ["Java", "Docker"], "job_hops": 4},
                },
                {
                    "name": "Chris",
                    "source_channel": "boss",
                    "external_candidate_id": "cand-ai-score-3",
                    "resume_text": "Python FastAPI",
                    "raw_profile": {"skills": ["Python"], "job_hops": 2},
                },
            ]
        },
    )
    assert response.status_code == 201
    return [item["id"] for item in response.json()["data"]["candidates"]]


def test_ai_batch_score_and_rank_workflow() -> None:
    job_id = _create_job()
    candidate_ids = _import_candidates()

    parse_response = client.post("/api/v1/ai/resume/parse", json={"candidate_id": candidate_ids[2]})
    assert parse_response.status_code == 200

    score_response = client.post(
        "/api/v1/ai/candidates/score",
        json={"job_id": job_id, "candidate_ids": candidate_ids},
    )
    assert score_response.status_code == 200
    score_payload = score_response.json()["data"]
    assert score_payload["job_id"] == job_id
    assert score_payload["scored_count"] == 3
    assert len(score_payload["results"]) == 3
    assert score_payload["results"][0]["total_score"] >= score_payload["results"][1]["total_score"]
    assert "risk_tags" in score_payload["results"][0]
    assert score_payload["results"][0]["score_version"] == "ai-score-v1"

    rank_response = client.post(
        "/api/v1/ai/candidates/rank",
        json={"job_id": job_id, "top_n": 2},
    )
    assert rank_response.status_code == 200
    rank_payload = rank_response.json()["data"]
    assert rank_payload["job_id"] == job_id
    assert rank_payload["top_n"] == 2
    assert len(rank_payload["shortlist"]) == 2
    assert rank_payload["shortlist"][0]["rank"] == 1
    assert rank_payload["shortlist"][1]["rank"] == 2
    assert rank_payload["shortlist"][0]["total_score"] >= rank_payload["shortlist"][1]["total_score"]

    shortlist_response = client.get(f"/api/v1/jobs/{job_id}/shortlist")
    assert shortlist_response.status_code == 200
    shortlist_payload = shortlist_response.json()["data"]
    assert shortlist_payload["job_id"] == job_id
    assert len(shortlist_payload["shortlist"]) == 2
    assert shortlist_payload["shortlist"][0]["rank"] == 1
    assert shortlist_payload["shortlist"][0]["candidate"]["id"] == rank_payload["shortlist"][0]["candidate"]["id"]


def test_rank_without_scores_returns_domain_error() -> None:
    job_id = _create_job()
    response = client.post("/api/v1/ai/candidates/rank", json={"job_id": job_id, "top_n": 3})
    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "domain_error"

