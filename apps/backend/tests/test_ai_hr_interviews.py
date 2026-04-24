from __future__ import annotations

from fastapi.testclient import TestClient
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_hr.connectors.base import ConnectorCredentials
from ai_hr.connectors.boss import BossConnector
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
            "title": "Backend Engineer",
            "department": "Engineering",
            "city": "Shanghai",
            "salary_range": "30k-45k",
            "requirements": "Python FastAPI MySQL",
        },
    )
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _create_candidate() -> str:
    external_id = f"cand-intv-{uuid.uuid4()}"
    response = client.post(
        "/api/v1/candidates/import",
        json={
            "candidates": [
                {
                    "name": "Interview Candidate",
                    "source_channel": "boss",
                    "external_candidate_id": external_id,
                    "resume_text": "Python FastAPI",
                    "raw_profile": {"skills": ["Python", "FastAPI"]},
                }
            ]
        },
    )
    assert response.status_code == 201
    return response.json()["data"]["candidates"][0]["id"]


def _create_shortlist(job_id: str, count: int) -> list[str]:
    """导入候选人并生成 shortlist，返回 top-N 候选人 ID。"""
    candidates = []
    for index in range(count):
        candidates.append(
            {
                "name": f"Candidate-{index}",
                "source_channel": "boss",
                "external_candidate_id": f"cand-shortlist-{uuid.uuid4()}",
                "resume_text": "Python FastAPI MySQL",
                "raw_profile": {"skills": ["Python", "FastAPI", "MySQL"], "job_hops": index},
            }
        )
    import_resp = client.post("/api/v1/candidates/import", json={"candidates": candidates})
    assert import_resp.status_code == 201
    candidate_ids = [item["id"] for item in import_resp.json()["data"]["candidates"]]

    score_resp = client.post(
        "/api/v1/ai/candidates/score",
        json={"job_id": job_id, "candidate_ids": candidate_ids},
    )
    assert score_resp.status_code == 200
    rank_resp = client.post("/api/v1/ai/candidates/rank", json={"job_id": job_id, "top_n": count})
    assert rank_resp.status_code == 200
    return [item["candidate"]["id"] for item in rank_resp.json()["data"]["shortlist"]]


def test_schedule_dispatch_and_sync_interview_workflow() -> None:
    job_id = _create_job()
    candidate_id = _create_candidate()

    schedule_response = client.post(
        "/api/v1/interviews/schedule",
        json={
            "candidate_id": candidate_id,
            "job_id": job_id,
            "channel": "boss",
            "scheduled_at": "2026-03-21T10:00:00",
            "meeting_link": "https://meeting.example.com/abc",
            "meeting_provider": "tencent_meeting",
            "note": "请提前10分钟进入会议",
            "auto_dispatch": False,
        },
    )
    assert schedule_response.status_code == 201
    schedule_payload = schedule_response.json()["data"]
    assert schedule_payload["interview"]["status"] == "pending"
    assert schedule_payload["dispatched"] is False
    interview_id = schedule_payload["interview"]["id"]

    dispatch_response = client.post(f"/api/v1/interviews/{interview_id}/dispatch", json={"force": True})
    assert dispatch_response.status_code == 200
    dispatch_payload = dispatch_response.json()["data"]
    assert dispatch_payload["status"] == "scheduled"
    assert dispatch_payload["interview"]["external_interview_id"] is not None

    sync_response = client.post(f"/api/v1/interviews/{interview_id}/sync-status", json={"force": True})
    assert sync_response.status_code == 200
    sync_payload = sync_response.json()["data"]
    assert sync_payload["status"] == "scheduled"
    assert sync_payload["interview"]["status"] == "scheduled"


def test_sync_interview_status_without_external_id_returns_domain_error() -> None:
    job_id = _create_job()
    candidate_id = _create_candidate()

    schedule_response = client.post(
        "/api/v1/interviews/schedule",
        json={
            "candidate_id": candidate_id,
            "job_id": job_id,
            "channel": "boss",
            "scheduled_at": "2026-03-22T10:00:00",
            "auto_dispatch": False,
        },
    )
    interview_id = schedule_response.json()["data"]["interview"]["id"]
    sync_response = client.post(f"/api/v1/interviews/{interview_id}/sync-status", json={})
    assert sync_response.status_code == 400
    assert sync_response.json()["error"]["code"] == "domain_error"


def test_boss_live_schedule_interview_success(monkeypatch) -> None:
    credentials = ConnectorCredentials(
        account="live-account",
        secret="live-secret",
        mode="live",
        base_url="https://www.zhipin.com",
        publish_path="/wapi/zpjob/job/publish.json",
        status_path="/wapi/zpjob/job/status.json",
        applicants_path="/wapi/zpjob/job/applicants.json",
        interview_schedule_path="/wapi/zpinterview/interview/schedule.json",
        interview_status_path="/wapi/zpinterview/interview/status.json",
        cookie_header="wt2=aaa; __zp_stoken__=bbb",
        timeout_seconds=3,
    )
    connector = BossConnector(credentials)
    connector.validate_credentials()

    def fake_send_live_request(_url, payload):
        assert payload["candidateId"] == "cand-1"
        return {"code": 0, "zpData": {"interviewId": "intv-live-1", "status": "SCHEDULED"}}

    monkeypatch.setattr(connector, "_send_live_request", fake_send_live_request)
    result = connector.schedule_interview(
        "cand-1",
        {
            "scheduled_at": "2026-03-21T10:00:00",
            "meeting_link": "https://meeting.example.com/abc",
            "meeting_provider": "tencent_meeting",
        },
    )
    assert result["external_interview_id"] == "intv-live-1"
    assert result["status"] == "scheduled"


def test_boss_live_sync_interview_status_success(monkeypatch) -> None:
    credentials = ConnectorCredentials(
        account="live-account",
        secret="live-secret",
        mode="live",
        base_url="https://www.zhipin.com",
        publish_path="/wapi/zpjob/job/publish.json",
        status_path="/wapi/zpjob/job/status.json",
        applicants_path="/wapi/zpjob/job/applicants.json",
        interview_schedule_path="/wapi/zpinterview/interview/schedule.json",
        interview_status_path="/wapi/zpinterview/interview/status.json",
        cookie_header="wt2=aaa; __zp_stoken__=bbb",
        timeout_seconds=3,
    )
    connector = BossConnector(credentials)
    connector.validate_credentials()

    def fake_send_live_request(_url, payload):
        assert payload["interviewId"] == "intv-live-1"
        return {"code": 0, "zpData": {"status": "CONFIRMED"}}

    monkeypatch.setattr(connector, "_send_live_request", fake_send_live_request)
    result = connector.sync_interview_status("intv-live-1")
    assert result["external_interview_id"] == "intv-live-1"
    assert result["status"] == "confirmed"


def test_job_interview_plan_and_send_progress_workflow() -> None:
    job_id = _create_job()
    shortlist_candidate_ids = _create_shortlist(job_id, count=3)

    plan_resp = client.post(f"/api/v1/jobs/{job_id}/interview/plan", json={"headcount": 2})
    assert plan_resp.status_code == 200
    plan_payload = plan_resp.json()["data"]
    assert plan_payload["planned_count"] == 2
    assert [item["candidate_id"] for item in plan_payload["plan"]] == shortlist_candidate_ids[:2]

    send_resp = client.post(
        f"/api/v1/jobs/{job_id}/interview/send",
        json={
            "headcount": 2,
            "channel": "boss",
            "scheduled_at": "2026-03-25T14:00:00",
            "meeting_link": "https://meeting.example.com/interview",
            "meeting_provider": "tencent_meeting",
            "note": "请提前10分钟进入会议",
            "auto_dispatch": True,
        },
    )
    assert send_resp.status_code == 200
    send_payload = send_resp.json()["data"]
    assert send_payload["attempted"] == 2
    assert send_payload["created"] == 2
    assert send_payload["sent"] == 2
    assert send_payload["failed"] == 0

    progress_resp = client.get(f"/api/v1/jobs/{job_id}/interview/progress")
    assert progress_resp.status_code == 200
    progress_payload = progress_resp.json()["data"]
    assert progress_payload["total_target"] == 2
    assert progress_payload["sent"] == 2
    assert progress_payload["success"] >= 2
    assert progress_payload["failed"] == 0


def test_job_interview_plan_no_shortlist_and_send_idempotent() -> None:
    job_id = _create_job()

    # Plan should be empty when there is no shortlist.
    # Plan should be empty when there is no shortlist.
    plan_resp = client.post(f"/api/v1/jobs/{job_id}/interview/plan", json={"headcount": 2})
    assert plan_resp.status_code == 200
    assert plan_resp.json()["data"]["planned_count"] == 0

    # First send creates one invitation; repeated send remains idempotent.
    _create_shortlist(job_id, count=2)
    first_send = client.post(
        f"/api/v1/jobs/{job_id}/interview/send",
        json={
            "headcount": 1,
            "channel": "boss",
            "scheduled_at": "2026-03-26T09:30:00",
            "auto_dispatch": False,
        },
    )
    assert first_send.status_code == 200
    assert first_send.json()["data"]["created"] == 1

    second_send = client.post(
        f"/api/v1/jobs/{job_id}/interview/send",
        json={
            "headcount": 1,
            "channel": "boss",
            "scheduled_at": "2026-03-26T09:30:00",
            "auto_dispatch": False,
        },
    )
    assert second_send.status_code == 200
    payload = second_send.json()["data"]
    assert payload["created"] == 0
    assert payload["attempted"] == 0


def test_job_interview_plan_never_exceeds_headcount() -> None:
    job_id = _create_job()
    _create_shortlist(job_id, count=4)

    send_resp = client.post(
        f"/api/v1/jobs/{job_id}/interview/send",
        json={
            "headcount": 2,
            "channel": "boss",
            "scheduled_at": "2026-03-27T11:00:00",
            "auto_dispatch": False,
        },
    )
    assert send_resp.status_code == 200
    assert send_resp.json()["data"]["created"] == 2

    # A second plan should still never exceed headcount.
    # A second plan should still never exceed headcount.
    plan_resp = client.post(f"/api/v1/jobs/{job_id}/interview/plan", json={"headcount": 2})
    assert plan_resp.status_code == 200
    assert plan_resp.json()["data"]["planned_count"] == 0
