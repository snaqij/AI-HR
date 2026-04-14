from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_hr.db.base import Base
from ai_hr.db.models import CandidateJobEvaluation, CandidateJobPipeline, CandidateJobScore, JobCandidate
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
            "title": "Java Backend Engineer",
            "department": "Engineering",
            "city": "Shanghai",
            "salary_range": "25k-35k",
            "requirements": "Java SpringBoot MySQL Redis 本科 3年以上",
        },
    )
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _create_candidate() -> str:
    response = client.post(
        "/api/v1/candidates/import",
        json={
            "candidates": [
                {
                    "name": "Guo Xiangqian",
                    "source_channel": "boss",
                    "external_candidate_id": "boss-eval-001",
                    "resume_text": "3年Java后端开发经验，本科，熟悉SpringBoot、MySQL、Redis，参与电商交易系统与库存系统开发。",
                    "raw_profile": {
                        "skills": ["Java", "SpringBoot", "MySQL", "Redis"],
                        "job_hops": 1,
                        "projects": [{"name": "交易系统", "role": "后端开发"}],
                    },
                }
            ]
        },
    )
    assert response.status_code == 201
    return response.json()["data"]["candidates"][0]["id"]


def _link_candidate_to_job(job_id: str, candidate_id: str) -> None:
    with TestingSessionLocal() as session:
        session.add(
            JobCandidate(
                job_id=job_id,
                publication_id=None,
                candidate_id=candidate_id,
                channel="boss",
                external_job_id="boss-job-001",
                external_candidate_id="boss-eval-001",
                stage="new",
                source_status="active",
                first_synced_at=datetime(2026, 4, 13, 0, 0, 0),
                last_synced_at=datetime(2026, 4, 13, 0, 0, 0),
                source_payload={},
            )
        )
        session.commit()


def test_candidate_evaluation_should_persist_evaluation_pipeline_and_score() -> None:
    job_id = _create_job()
    candidate_id = _create_candidate()
    _link_candidate_to_job(job_id, candidate_id)

    response = client.post(
        f"/api/v1/jobs/{job_id}/candidates/{candidate_id}/evaluate",
        json={"evaluation_version": "v1"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["candidate"]["id"] == candidate_id
    assert payload["evaluation"]["job_id"] == job_id
    assert payload["evaluation"]["final_score"] > 0
    assert payload["pipeline_status"]["evaluation_status"] == "completed"

    with TestingSessionLocal() as session:
        evaluation = session.execute(
            select(CandidateJobEvaluation).where(
                CandidateJobEvaluation.candidate_id == candidate_id,
                CandidateJobEvaluation.job_id == job_id,
            )
        ).scalar_one()
        pipeline = session.execute(
            select(CandidateJobPipeline).where(
                CandidateJobPipeline.candidate_id == candidate_id,
                CandidateJobPipeline.job_id == job_id,
            )
        ).scalar_one()
        job_score = session.execute(
            select(CandidateJobScore).where(
                CandidateJobScore.candidate_id == candidate_id,
                CandidateJobScore.job_id == job_id,
            )
        ).scalar_one()
        assert evaluation.candidate_id == candidate_id
        assert pipeline.latest_evaluation_id == evaluation.id
        assert job_score.job_id == job_id
        assert float(job_score.total_score) == payload["evaluation"]["final_score"]


def test_job_evaluation_list_should_return_created_evaluations() -> None:
    job_id = _create_job()
    candidate_id = _create_candidate()
    _link_candidate_to_job(job_id, candidate_id)
    evaluate_response = client.post(
        f"/api/v1/jobs/{job_id}/candidates/{candidate_id}/evaluate",
        json={"evaluation_version": "v1"},
    )
    assert evaluate_response.status_code == 200

    response = client.get(f"/api/v1/jobs/{job_id}/evaluations")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["job_id"] == job_id
    assert payload["total"] >= 1
    assert payload["items"][0]["candidate"]["id"] == candidate_id
