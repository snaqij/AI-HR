from __future__ import annotations

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_hr.connectors.base import ConnectorCredentials
from ai_hr.connectors.boss import BossConnector
from ai_hr.core.exceptions import ConnectorOperationError
from ai_hr.db.base import Base
from ai_hr.db.models import Candidate, CandidateIdentity
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


def test_create_job_returns_envelope() -> None:
    response = client.post(
        "/api/v1/jobs",
        json={
            "title": "Senior Backend Engineer",
            "department": "Engineering",
            "city": "Shanghai",
            "salary_range": "30k-45k",
            "requirements": "FastAPI, MySQL, distributed systems",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["title"] == "Senior Backend Engineer"
    assert payload["data"]["status"] == "draft"


def test_publish_job_creates_publication_record() -> None:
    create_response = client.post(
        "/api/v1/jobs",
        json={
            "title": "Platform Engineer",
            "department": "Engineering",
            "city": "Beijing",
            "salary_range": "35k-50k",
            "requirements": "Python, FastAPI, event driven design",
        },
    )
    job_id = create_response.json()["data"]["id"]

    publish_response = client.post(
        f"/api/v1/jobs/{job_id}/publish",
        json={"channels": ["boss"]},
    )

    assert publish_response.status_code == 200
    payload = publish_response.json()
    assert payload["ok"] is True
    assert payload["data"]["job"]["status"] == "published"
    assert len(payload["data"]["publications"]) == 1
    assert payload["data"]["publications"][0]["channel"] == "boss"
    assert payload["data"]["publications"][0]["status"] == "published"


def test_import_candidates_upserts_by_external_identity() -> None:
    first_response = client.post(
        "/api/v1/candidates/import",
        json={
            "candidates": [
                {
                    "name": "Alice",
                    "source_channel": "boss",
                    "external_candidate_id": "cand-1",
                    "resume_url": "https://example.com/resume-1.pdf",
                    "resume_text": "FastAPI and Python",
                    "raw_profile": {"skills": ["FastAPI", "Python"]},
                }
            ]
        },
    )

    assert first_response.status_code == 201
    first_payload = first_response.json()
    assert first_payload["data"]["created_count"] == 1
    assert first_payload["data"]["updated_count"] == 0

    second_response = client.post(
        "/api/v1/candidates/import",
        json={
            "candidates": [
                {
                    "name": "Alice Zhang",
                    "source_channel": "boss",
                    "external_candidate_id": "cand-1",
                    "resume_url": "https://example.com/resume-1-v2.pdf",
                    "resume_text": "FastAPI, Python, MySQL",
                    "raw_profile": {"skills": ["FastAPI", "Python", "MySQL"]},
                }
            ]
        },
    )

    assert second_response.status_code == 201
    second_payload = second_response.json()
    assert second_payload["data"]["created_count"] == 0
    assert second_payload["data"]["updated_count"] == 1
    assert second_payload["data"]["candidates"][0]["name"] == "Alice Zhang"


def test_import_candidates_merges_same_person_with_different_external_ids() -> None:
    first_response = client.post(
        "/api/v1/candidates/import",
        json={
            "candidates": [
                {
                    "name": "Bob Li",
                    "source_channel": "boss",
                    "external_candidate_id": "cand-merge-1",
                    "phone_hash": "phone-hash-001",
                    "resume_text": "Python",
                    "raw_profile": {"skills": ["Python"]},
                }
            ]
        },
    )
    assert first_response.status_code == 201
    candidate_id = first_response.json()["data"]["candidates"][0]["id"]

    second_response = client.post(
        "/api/v1/candidates/import",
        json={
            "candidates": [
                {
                    "name": "Bob Li Updated",
                    "source_channel": "boss",
                    "external_candidate_id": "cand-merge-2",
                    "phone_hash": "phone-hash-001",
                    "resume_text": "Python, FastAPI",
                    "raw_profile": {"skills": ["Python", "FastAPI"]},
                }
            ]
        },
    )
    assert second_response.status_code == 201
    payload = second_response.json()["data"]
    assert payload["created_count"] == 0
    assert payload["updated_count"] == 1
    assert payload["candidates"][0]["id"] == candidate_id
    assert payload["candidates"][0]["name"] == "Bob Li Updated"

    with TestingSessionLocal() as session:
        identities = session.execute(
            select(CandidateIdentity).where(
                CandidateIdentity.source_channel == "boss",
                CandidateIdentity.external_candidate_id.in_(["cand-merge-1", "cand-merge-2"]),
            )
        ).scalars().all()
        assert len(identities) == 2
        assert len({identity.candidate_id for identity in identities}) == 1

        mapped_candidate = session.get(Candidate, identities[0].candidate_id)
        assert mapped_candidate is not None
        assert mapped_candidate.name == "Bob Li Updated"


def test_publish_status_sync_calls_connector_and_updates_payload() -> None:
    create_response = client.post(
        "/api/v1/jobs",
        json={
            "title": "Backend Engineer",
            "department": "Engineering",
            "city": "Hangzhou",
            "salary_range": "30k-45k",
            "requirements": "Python, FastAPI, SQLAlchemy",
        },
    )
    job_id = create_response.json()["data"]["id"]

    publish_response = client.post(
        f"/api/v1/jobs/{job_id}/publish",
        json={"channels": ["boss"]},
    )
    assert publish_response.status_code == 200

    status_response = client.get(f"/api/v1/jobs/{job_id}/publish-status")
    assert status_response.status_code == 200
    payload = status_response.json()
    assert payload["ok"] is True
    assert len(payload["data"]["publications"]) == 1
    publication = payload["data"]["publications"][0]
    assert publication["channel"] == "boss"
    assert publication["status"] == "published"
    assert publication["response_payload"]["mode"] == "mock"


def test_sync_candidates_supports_incremental_cursor_pull() -> None:
    create_response = client.post(
        "/api/v1/jobs",
        json={
            "title": "Infra Engineer",
            "department": "Infrastructure",
            "city": "Shanghai",
            "salary_range": "30k-45k",
            "requirements": "Linux, Python, observability",
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
    first_payload = first_sync.json()["data"]
    assert first_payload["total_created"] == 1
    assert first_payload["total_updated"] == 0
    assert first_payload["channels"][0]["next_cursor"] == "cursor-1"
    assert first_payload["channels"][0]["has_more"] is True

    second_sync = client.post(
        f"/api/v1/jobs/{job_id}/candidates/sync",
        json={"channels": ["boss"], "max_pages": 1},
    )
    assert second_sync.status_code == 200
    second_payload = second_sync.json()["data"]
    assert second_payload["total_created"] == 1
    assert second_payload["total_updated"] == 0
    assert second_payload["channels"][0]["next_cursor"] == "cursor-2"
    assert second_payload["channels"][0]["has_more"] is True

    third_sync = client.post(
        f"/api/v1/jobs/{job_id}/candidates/sync",
        json={"channels": ["boss"], "max_pages": 1},
    )
    assert third_sync.status_code == 200
    third_payload = third_sync.json()["data"]
    assert third_payload["total_created"] == 0
    assert third_payload["total_updated"] == 0
    assert third_payload["channels"][0]["next_cursor"] is None
    assert third_payload["channels"][0]["has_more"] is False


def test_greet_sync_and_reply_workflow() -> None:
    import_response = client.post(
        "/api/v1/candidates/import",
        json={
            "candidates": [
                {
                    "name": "Daisy",
                    "source_channel": "boss",
                    "external_candidate_id": "cand-chat-1",
                    "resume_text": "Python FastAPI",
                    "raw_profile": {"skills": ["Python", "FastAPI"]},
                }
            ]
        },
    )
    assert import_response.status_code == 201
    candidate_id = import_response.json()["data"]["candidates"][0]["id"]

    greet_response = client.post(
        "/api/v1/conversations/greet",
        json={
            "candidate_id": candidate_id,
            "template_id": "default",
            "variables": {"name": "Daisy", "job_title": "Backend Engineer"},
        },
    )
    assert greet_response.status_code == 201
    greet_payload = greet_response.json()["data"]
    assert greet_payload["dispatched"] is True
    conversation_id = greet_payload["conversation"]["id"]
    assert greet_payload["conversation"]["channel"] == "boss"

    first_sync = client.post(f"/api/v1/conversations/{conversation_id}/sync", json={"max_pages": 1})
    assert first_sync.status_code == 200
    first_sync_payload = first_sync.json()["data"]
    assert first_sync_payload["pulled_count"] == 1
    assert first_sync_payload["has_more"] is True
    assert first_sync_payload["next_cursor"] == "cursor-1"

    second_sync = client.post(f"/api/v1/conversations/{conversation_id}/sync", json={"max_pages": 1})
    assert second_sync.status_code == 200
    second_sync_payload = second_sync.json()["data"]
    assert second_sync_payload["pulled_count"] == 1
    assert second_sync_payload["has_more"] is True
    assert second_sync_payload["next_cursor"] == "cursor-2"

    auto_reply = client.post(
        "/api/v1/conversations/reply",
        json={"conversation_id": conversation_id, "auto": True},
    )
    assert auto_reply.status_code == 200
    auto_reply_payload = auto_reply.json()["data"]
    assert auto_reply_payload["mode"] == "auto"
    assert auto_reply_payload["sent"] is False
    assert auto_reply_payload["confidence"] < 0.6
    assert auto_reply_payload["conversation"]["status"] == "needs_human"

    manual_reply = client.post(
        "/api/v1/conversations/reply",
        json={"conversation_id": conversation_id, "message": "收到，我们稍后安排沟通"},
    )
    assert manual_reply.status_code == 200
    manual_payload = manual_reply.json()["data"]
    assert manual_payload["mode"] == "manual"
    assert manual_payload["sent"] is True
    assert manual_payload["message"]["direction"] == "outbound"


def test_score_candidate_writes_back_result_and_stage() -> None:
    job_response = client.post(
        "/api/v1/jobs",
        json={
            "title": "Backend Engineer",
            "department": "Engineering",
            "city": "Shanghai",
            "salary_range": "30k-45k",
            "requirements": "Python FastAPI MySQL",
        },
    )
    job_id = job_response.json()["data"]["id"]

    import_response = client.post(
        "/api/v1/candidates/import",
        json={
            "candidates": [
                {
                    "name": "Chris",
                    "source_channel": "boss",
                    "external_candidate_id": "cand-score-1",
                    "resume_text": "I use Python FastAPI and MySQL in production",
                    "raw_profile": {"skills": ["Python", "FastAPI", "MySQL"]},
                }
            ]
        },
    )
    candidate_id = import_response.json()["data"]["candidates"][0]["id"]

    score_response = client.post(
        f"/api/v1/candidates/{candidate_id}/score",
        json={"job_id": job_id},
    )

    assert score_response.status_code == 200
    payload = score_response.json()["data"]
    assert payload["total_score"] >= 0
    assert set(payload["dimensions"].keys()) == {"skills_match", "experience_relevance", "stability"}
    assert payload["candidate"]["score_total"] == payload["total_score"]
    assert payload["candidate"]["score_explanation"] is not None
    assert payload["candidate"]["scored_at"] is not None
    assert payload["candidate"]["current_stage"] in {"parsed", "screen_pass"}


def test_score_missing_candidate_returns_404() -> None:
    response = client.post("/api/v1/candidates/missing-id/score", json={})

    assert response.status_code == 404
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "not_found"


def test_boss_live_publish_job_success(monkeypatch) -> None:
    credentials = ConnectorCredentials(
        account="live-account",
        secret="live-secret",
        mode="live",
        base_url="https://www.zhipin.com",
        publish_path="/wapi/zpjob/job/publish.json",
        status_path="/wapi/zpjob/job/status.json",
        applicants_path="/wapi/zpjob/job/applicants.json",
        cookie_header="wt2=aaa; __zp_stoken__=bbb",
        timeout_seconds=3,
    )
    connector = BossConnector(credentials)
    connector.validate_credentials()

    def fake_send_publish_request(payload):
        assert payload["jobName"] == "Senior Backend Engineer"
        return {"code": 0, "zpData": {"jobId": "boss-live-job-1"}}

    monkeypatch.setattr(connector, "_send_publish_request", fake_send_publish_request)
    result = connector.publish_job(
        {
            "title": "Senior Backend Engineer",
            "requirements": "Python FastAPI MySQL",
            "city": "Shanghai",
            "salary_range": "30k-45k",
            "department": "Engineering",
        }
    )
    assert result.status == "published"
    assert result.external_job_id == "boss-live-job-1"


def test_boss_live_publish_job_handles_remote_error(monkeypatch) -> None:
    credentials = ConnectorCredentials(
        account="live-account",
        secret="live-secret",
        mode="live",
        base_url="https://www.zhipin.com",
        publish_path="/wapi/zpjob/job/publish.json",
        status_path="/wapi/zpjob/job/status.json",
        applicants_path="/wapi/zpjob/job/applicants.json",
        cookie_header="wt2=aaa; __zp_stoken__=bbb",
        timeout_seconds=3,
    )
    connector = BossConnector(credentials)
    connector.validate_credentials()

    def fake_send_publish_request(_payload):
        raise ConnectorOperationError("BOSS publish failed: code=403, message=forbidden")

    monkeypatch.setattr(connector, "_send_publish_request", fake_send_publish_request)

    with pytest.raises(ConnectorOperationError):
        connector.publish_job(
            {
                "title": "Senior Backend Engineer",
                "requirements": "Python FastAPI MySQL",
                "city": "Shanghai",
                "salary_range": "30k-45k",
                "department": "Engineering",
            }
        )


def test_boss_live_sync_job_status_success(monkeypatch) -> None:
    credentials = ConnectorCredentials(
        account="live-account",
        secret="live-secret",
        mode="live",
        base_url="https://www.zhipin.com",
        publish_path="/wapi/zpjob/job/publish.json",
        status_path="/wapi/zpjob/job/status.json",
        applicants_path="/wapi/zpjob/job/applicants.json",
        cookie_header="wt2=aaa; __zp_stoken__=bbb",
        timeout_seconds=3,
    )
    connector = BossConnector(credentials)
    connector.validate_credentials()

    def fake_send_status_request(external_job_id):
        assert external_job_id == "boss-live-job-1"
        return {"code": 0, "zpData": {"status": "PUBLISHED"}}

    monkeypatch.setattr(connector, "_send_status_request", fake_send_status_request)
    result = connector.sync_job_status("boss-live-job-1")
    assert result.status == "published"
    assert result.external_job_id == "boss-live-job-1"


def test_boss_live_list_applicants_success(monkeypatch) -> None:
    credentials = ConnectorCredentials(
        account="live-account",
        secret="live-secret",
        mode="live",
        base_url="https://www.zhipin.com",
        publish_path="/wapi/zpjob/job/publish.json",
        status_path="/wapi/zpjob/job/status.json",
        applicants_path="/wapi/zpjob/job/applicants.json",
        cookie_header="wt2=aaa; __zp_stoken__=bbb",
        timeout_seconds=3,
    )
    connector = BossConnector(credentials)
    connector.validate_credentials()

    def fake_send_list_applicants_request(job_external_id, cursor=None):
        assert job_external_id == "boss-live-job-1"
        assert cursor == "cursor-1"
        return {
            "code": 0,
            "zpData": {
                "geekList": [
                    {
                        "geekId": "cand-1",
                        "geekName": "Alice",
                        "resumeUrl": "https://example.com/a.pdf",
                        "resumeText": "Python FastAPI",
                    }
                ],
                "nextCursor": "cursor-2",
                "hasMore": True,
            },
        }

    monkeypatch.setattr(connector, "_send_list_applicants_request", fake_send_list_applicants_request)
    result = connector.list_applicants("boss-live-job-1", cursor="cursor-1")
    assert result["next_cursor"] == "cursor-2"
    assert result["has_more"] is True
    assert len(result["items"]) == 1
    assert result["items"][0]["external_candidate_id"] == "cand-1"
    assert result["items"][0]["name"] == "Alice"


def test_boss_live_send_greeting_success(monkeypatch) -> None:
    credentials = ConnectorCredentials(
        account="live-account",
        secret="live-secret",
        mode="live",
        base_url="https://www.zhipin.com",
        publish_path="/wapi/zpjob/job/publish.json",
        status_path="/wapi/zpjob/job/status.json",
        applicants_path="/wapi/zpjob/job/applicants.json",
        greet_path="/wapi/zpchat/greet/send.json",
        fetch_messages_path="/wapi/zpchat/conversation/messages.json",
        send_message_path="/wapi/zpchat/conversation/send.json",
        cookie_header="wt2=aaa; __zp_stoken__=bbb",
        timeout_seconds=3,
    )
    connector = BossConnector(credentials)
    connector.validate_credentials()

    def fake_send_live_request(_url, payload):
        assert payload["candidateId"] == "cand-1"
        return {"code": 0, "zpData": {"conversationId": "conv-1", "messageId": "msg-1", "content": "hi"}}

    monkeypatch.setattr(connector, "_send_live_request", fake_send_live_request)
    result = connector.send_greeting("cand-1", "default", {"name": "Alice"})
    assert result["external_conversation_id"] == "conv-1"
    assert result["message_id"] == "msg-1"


def test_boss_live_fetch_messages_success(monkeypatch) -> None:
    credentials = ConnectorCredentials(
        account="live-account",
        secret="live-secret",
        mode="live",
        base_url="https://www.zhipin.com",
        publish_path="/wapi/zpjob/job/publish.json",
        status_path="/wapi/zpjob/job/status.json",
        applicants_path="/wapi/zpjob/job/applicants.json",
        greet_path="/wapi/zpchat/greet/send.json",
        fetch_messages_path="/wapi/zpchat/conversation/messages.json",
        send_message_path="/wapi/zpchat/conversation/send.json",
        cookie_header="wt2=aaa; __zp_stoken__=bbb",
        timeout_seconds=3,
    )
    connector = BossConnector(credentials)
    connector.validate_credentials()

    def fake_send_live_request(_url, payload):
        assert payload["conversationId"] == "conv-1"
        return {
            "code": 0,
            "zpData": {
                "messages": [{"messageId": "m1", "sender": "candidate", "content": "hello"}],
                "nextCursor": "n2",
                "hasMore": True,
            },
        }

    monkeypatch.setattr(connector, "_send_live_request", fake_send_live_request)
    result = connector.fetch_messages("conv-1", cursor="c1")
    assert len(result["messages"]) == 1
    assert result["messages"][0]["external_message_id"] == "m1"
    assert result["next_cursor"] == "n2"
    assert result["has_more"] is True


def test_boss_live_send_message_success(monkeypatch) -> None:
    credentials = ConnectorCredentials(
        account="live-account",
        secret="live-secret",
        mode="live",
        base_url="https://www.zhipin.com",
        publish_path="/wapi/zpjob/job/publish.json",
        status_path="/wapi/zpjob/job/status.json",
        applicants_path="/wapi/zpjob/job/applicants.json",
        greet_path="/wapi/zpchat/greet/send.json",
        fetch_messages_path="/wapi/zpchat/conversation/messages.json",
        send_message_path="/wapi/zpchat/conversation/send.json",
        cookie_header="wt2=aaa; __zp_stoken__=bbb",
        timeout_seconds=3,
    )
    connector = BossConnector(credentials)
    connector.validate_credentials()

    def fake_send_live_request(_url, payload):
        assert payload["conversationId"] == "conv-1"
        assert payload["message"] == "你好"
        return {"code": 0, "zpData": {"messageId": "m-out-1"}}

    monkeypatch.setattr(connector, "_send_live_request", fake_send_live_request)
    result = connector.send_message("conv-1", "你好")
    assert result["status"] == "sent"
    assert result["message_id"] == "m-out-1"


def test_get_missing_job_returns_404_envelope() -> None:
    response = client.get("/api/v1/jobs/missing")

    assert response.status_code == 404
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "not_found"


def test_create_job_is_idempotent_with_same_key() -> None:
    headers = {"X-Idempotency-Key": "job-create-001"}
    payload = {
        "title": "SRE Engineer",
        "department": "Infrastructure",
        "city": "Shenzhen",
        "salary_range": "32k-48k",
        "requirements": "Kubernetes, observability, incident response",
    }

    first = client.post("/api/v1/jobs", json=payload, headers=headers)
    second = client.post("/api/v1/jobs", json=payload, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["data"]["id"] == second.json()["data"]["id"]


def test_create_job_rejects_different_payload_with_same_key() -> None:
    headers = {"X-Idempotency-Key": "job-create-002"}
    first_payload = {
        "title": "Data Engineer",
        "department": "Data",
        "city": "Shanghai",
        "salary_range": "28k-42k",
        "requirements": "Python, ETL, data warehouse",
    }
    second_payload = {
        "title": "Data Engineer II",
        "department": "Data",
        "city": "Shanghai",
        "salary_range": "30k-45k",
        "requirements": "Python, ETL, streaming",
    }

    first = client.post("/api/v1/jobs", json=first_payload, headers=headers)
    second = client.post("/api/v1/jobs", json=second_payload, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["ok"] is False
    assert second.json()["error"]["code"] == "idempotency_conflict"


def test_core_tables_are_registered() -> None:
    expected_tables = {"jobs", "candidates", "candidate_identities", "job_publications", "conversations", "interviews", "events"}
    assert expected_tables.issubset(set(Base.metadata.tables.keys()))
