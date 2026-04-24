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
            "title": "Governance Backend Engineer",
            "department": "Engineering",
            "city": "Shanghai",
            "salary_range": "30k-45k",
            "requirements": "Python FastAPI MySQL",
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
                    "name": "Governance Candidate",
                    "source_channel": "boss",
                    "external_candidate_id": "cand-governance-1",
                    "resume_text": "Python FastAPI",
                    "raw_profile": {"skills": ["Python", "FastAPI"]},
                }
            ]
        },
    )
    assert response.status_code == 201
    return response.json()["data"]["candidates"][0]["id"]


def _create_interview(job_id: str, candidate_id: str) -> str:
    response = client.post(
        "/api/v1/interviews/schedule",
        json={
            "candidate_id": candidate_id,
            "job_id": job_id,
            "channel": "boss",
            "scheduled_at": "2026-03-21T10:00:00",
            "auto_dispatch": False,
        },
    )
    assert response.status_code == 201
    return response.json()["data"]["interview"]["id"]


def test_approval_create_decide_and_audit_query() -> None:
    create_resp = client.post(
        "/api/v1/approvals",
        json={
            "action_type": "interview_batch_send",
            "entity_type": "job",
            "entity_id": "job-governance-1",
            "requested_by": "hr_admin",
            "reason": "批量发送面试邀约前审批",
            "payload": {"job_id": "job-governance-1"},
        },
    )
    assert create_resp.status_code == 201
    approval = create_resp.json()["data"]
    assert approval["status"] == "pending"
    approval_id = approval["id"]

    decide_resp = client.post(
        f"/api/v1/approvals/{approval_id}/decision",
        json={
            "decision": "approved",
            "decided_by": "ops_lead",
            "note": "符合发送标准",
        },
    )
    assert decide_resp.status_code == 200
    decided = decide_resp.json()["data"]
    assert decided["status"] == "approved"
    assert decided["decided_by"] == "ops_lead"

    audit_resp = client.get("/api/v1/audit/events", params={"entity_type": "approval", "entity_id": approval_id, "limit": 20})
    assert audit_resp.status_code == 200
    audit_payload = audit_resp.json()["data"]
    assert audit_payload["total"] >= 2
    event_types = [item["event_type"] for item in audit_payload["items"]]
    assert "approval.created" in event_types
    assert "approval.approved" in event_types


def test_funnel_metrics_endpoint_available() -> None:
    job_id = _create_job()
    candidate_id = _create_candidate()
    _create_interview(job_id, candidate_id)

    approval_resp = client.post(
        "/api/v1/approvals",
        json={
            "action_type": "offer",
            "entity_type": "candidate",
            "entity_id": candidate_id,
            "requested_by": "hr_admin",
            "reason": "发放 offer 审批",
        },
    )
    approval_id = approval_resp.json()["data"]["id"]
    decide_resp = client.post(
        f"/api/v1/approvals/{approval_id}/decision",
        json={"decision": "approved", "decided_by": "director"},
    )
    assert decide_resp.status_code == 200

    funnel_resp = client.get("/api/v1/metrics/funnel")
    assert funnel_resp.status_code == 200
    stages = funnel_resp.json()["data"]["stages"]
    assert len(stages) >= 4
    stage_names = [item["stage"] for item in stages]
    assert "jobs" in stage_names
    assert "candidates" in stage_names
    assert "interviews" in stage_names
    assert "offer_approved" in stage_names


def test_audit_events_support_operator_session_job_filters() -> None:
    create_resp = client.post(
        "/api/v1/approvals",
        json={
            "action_type": "interview_batch_send",
            "entity_type": "job",
            "entity_id": "job-governance-filter-1",
            "requested_by": "hr_operator",
            "reason": "过滤能力验证",
        },
    )
    assert create_resp.status_code == 201
    approval_id = create_resp.json()["data"]["id"]

    decide_resp = client.post(
        f"/api/v1/approvals/{approval_id}/decision",
        json={"decision": "approved", "decided_by": "ops_filter"},
    )
    assert decide_resp.status_code == 200

    query_resp = client.get(
        "/api/v1/audit/events",
        params={
            "entity_type": "approval",
            "entity_id": approval_id,
            "operator": "ops_filter",
        },
    )
    assert query_resp.status_code == 200
    payload = query_resp.json()["data"]
    assert payload["total"] >= 1
    assert any(item.get("operator") == "ops_filter" for item in payload["items"])
