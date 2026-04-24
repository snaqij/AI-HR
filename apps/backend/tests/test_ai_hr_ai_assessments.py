from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_hr.db.base import Base
from ai_hr.db.models import CandidateCompositeAssessment, CandidateJobEvaluation, CandidateJobPipeline
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
    resp = client.post(
        "/api/v1/jobs",
        json={
            "title": "Enterprise AI Engineer",
            "department": "Engineering",
            "city": "Shanghai",
            "salary_range": "40k-60k",
            "requirements": "Python, FastAPI, distributed systems, ownership mindset",
        },
    )
    assert resp.status_code == 201
    return resp.json()["data"]["id"]


def _create_candidate() -> str:
    resp = client.post(
        "/api/v1/candidates/import",
        json={
            "candidates": [
                {
                    "name": "Composite Candidate",
                    "source_channel": "boss",
                    "external_candidate_id": "cand-assess-1",
                    "resume_text": "I built high-availability APIs with Python and FastAPI for three years.",
                    "raw_profile": {"skills": ["Python", "FastAPI", "MySQL"]},
                }
            ]
        },
    )
    assert resp.status_code == 201
    return resp.json()["data"]["candidates"][0]["id"]


def _create_and_start_session(job_id: str, candidate_id: str) -> str:
    create_resp = client.post(
        "/api/v1/ai/interviews/sessions",
        json={"candidate_id": candidate_id, "job_id": job_id},
    )
    assert create_resp.status_code == 201
    session_id = create_resp.json()["data"]["session"]["id"]
    start_resp = client.post(f"/api/v1/ai/interviews/sessions/{session_id}/start", json={})
    assert start_resp.status_code == 200
    return session_id


def test_event_ingest_and_interview_assessment_flow() -> None:
    job_id = _create_job()
    candidate_id = _create_candidate()
    session_id = _create_and_start_session(job_id, candidate_id)

    ask_resp = client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/events",
        json={
            "event_id": "evt-ask-1",
            "seq": 1,
            "speaker": "assistant",
            "transcript": "Please explain one project where you improved system reliability.",
            "payload": {
                "current_question_id": "q-tech-1",
                "current_question_seq": 1,
                "current_question_text": "Explain a reliability project you led.",
                "difficulty_level": "hard",
                "critical": True,
                "required": True,
            },
        },
    )
    assert ask_resp.status_code == 200

    answer_resp = client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/events",
        json={
            "event_id": "evt-answer-1",
            "seq": 2,
            "speaker": "candidate",
            "transcript": (
                "In 2025 I led a reliability refactor for our order service. "
                "First, we added circuit breakers and retriable queues, then reduced P95 latency by 38%."
            ),
            "confidence": 0.91,
            "payload": {
                "current_question_id": "q-tech-1",
                "current_question_seq": 1,
                "is_final_answer": True,
                "trace_id": "trace-qa-1",
            },
        },
    )
    assert answer_resp.status_code == 200
    answer_data = answer_resp.json()["data"]
    assert answer_data["accepted"] is True
    assert isinstance(answer_data.get("question_attempt_id"), str)

    compute_resp = client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/assessments/compute",
        json={"run_mode": "sync", "policy_code": "candidate_progression", "force_recompute": True},
    )
    assert compute_resp.status_code == 200
    compute_data = compute_resp.json()["data"]
    assert compute_data["status"] == "computed"
    assert isinstance(compute_data["assessment_id"], str)

    latest_resp = client.get(f"/api/v1/ai/interviews/sessions/{session_id}/assessments/latest")
    assert latest_resp.status_code == 200
    latest = latest_resp.json()["data"]
    assert latest["interview_score"] >= 0
    assert latest["coverage_rate"] >= 0
    assert latest["recommendation"] in {"advance", "manual_review", "reject"}


def test_composite_decision_override_publish_flow() -> None:
    job_id = _create_job()
    candidate_id = _create_candidate()
    session_id = _create_and_start_session(job_id, candidate_id)

    client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/events",
        json={
            "event_id": "evt-q-2",
            "seq": 1,
            "speaker": "assistant",
            "transcript": "Tell me about your impact.",
            "payload": {"current_question_id": "q-impact-1", "current_question_seq": 1, "required": True},
        },
    )
    client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/events",
        json={
            "event_id": "evt-a-2",
            "seq": 2,
            "speaker": "candidate",
            "transcript": "I improved conversion by 12% and reduced incident count by half in one quarter.",
            "confidence": 0.9,
            "payload": {"current_question_id": "q-impact-1", "current_question_seq": 1},
        },
    )
    interview_compute_resp = client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/assessments/compute",
        json={"run_mode": "sync", "force_recompute": True},
    )
    assert interview_compute_resp.status_code == 200

    with TestingSessionLocal() as db:
        db.add(
            CandidateJobEvaluation(
                candidate_id=candidate_id,
                job_id=job_id,
                evaluation_version="v1",
                source="hybrid",
                status="completed",
                match_score=86.0,
                competitiveness_score=83.0,
                final_score=88.0,
                confidence_score=84.0,
                recommendation="recommend",
                summary="Strong resume signal.",
                dimension_scores={"skills": 90.0, "experience": 86.0},
                strengths=["FastAPI", "system design"],
                weaknesses=[],
                highlights=["Ownership", "delivery"],
                risk_flags=[],
                job_requirement_coverage={"coverage": 0.82},
                raw_llm_output={},
            )
        )
        db.commit()

    composite_compute_resp = client.post(
        "/api/v1/ai/composite-assessments/compute",
        json={
            "candidate_id": candidate_id,
            "job_id": job_id,
            "session_id": session_id,
            "market_context": {"region": "cn", "industry": "internet", "level": "senior"},
        },
    )
    assert composite_compute_resp.status_code == 200
    composite_data = composite_compute_resp.json()["data"]
    composite_id = composite_data["composite_assessment_id"]
    assert composite_data["composite_score"] >= 0

    decide_resp = client.post(
        f"/api/v1/ai/composite-assessments/{composite_id}/decide",
        json={"policy_code": "candidate_progression", "dry_run": False},
    )
    assert decide_resp.status_code == 200
    decide_data = decide_resp.json()["data"]
    assert decide_data["decision"] in {"advance", "manual_review", "reject"}
    assert decide_data["next_step_status"] in {"invited", "hold", "rejected"}

    override_resp = client.post(
        f"/api/v1/ai/composite-assessments/{composite_id}/override",
        json={
            "operator_id": "hrbp-1",
            "decision": "manual_review",
            "reason_code": "business_priority",
            "note": "Need one more human interview for calibration.",
        },
    )
    assert override_resp.status_code == 200
    override_data = override_resp.json()["data"]
    assert override_data["human_override"] is True
    assert override_data["updated_pipeline_status"] == "hold"

    review_tasks_resp = client.get("/api/v1/ai/review-queue/tasks", params={"status": "open"})
    assert review_tasks_resp.status_code == 200
    assert "items" in review_tasks_resp.json()["data"]

    with TestingSessionLocal() as db:
        composite = db.get(CandidateCompositeAssessment, composite_id)
        assert composite is not None
        pipeline = db.execute(
            select(CandidateJobPipeline).where(
                CandidateJobPipeline.candidate_id == candidate_id,
                CandidateJobPipeline.job_id == job_id,
            )
        ).scalars().first()
        assert pipeline is not None
        publish_resp = client.post(
            f"/api/v1/pipelines/{pipeline.id}/next-step/publish",
            json={"assessment_id": composite_id, "expected_version": composite.composite_version},
        )
        assert publish_resp.status_code == 200
        assert publish_resp.json()["data"]["next_step_status"] in {"invited", "hold", "rejected"}
