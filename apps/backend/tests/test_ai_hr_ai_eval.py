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


def test_run_eval_and_query_latest_report() -> None:
    run_resp = client.post(
        "/api/v1/ai/eval/run",
        json={
            "eval_type": "resume_parse",
            "dataset_version": "v1",
            "model_version": "mock-1",
        },
    )
    assert run_resp.status_code == 200
    run_payload = run_resp.json()["data"]
    assert run_payload["status"] == "completed"
    assert run_payload["eval_type"] == "resume_parse"
    assert "run_id" in run_payload
    assert "parse_success_rate" in run_payload["metrics"]

    report_resp = client.get("/api/v1/ai/eval/report", params={"eval_type": "resume_parse"})
    assert report_resp.status_code == 200
    report_payload = report_resp.json()["data"]
    assert report_payload["eval_type"] == "resume_parse"
    assert report_payload["run_id"] == run_payload["run_id"]


def test_query_report_by_run_id() -> None:
    run_resp = client.post(
        "/api/v1/ai/eval/run",
        json={
            "eval_type": "reply_generate",
            "dataset_version": "v2",
            "model_version": "mock-2",
        },
    )
    assert run_resp.status_code == 200
    run_id = run_resp.json()["data"]["run_id"]

    report_resp = client.get(
        "/api/v1/ai/eval/report",
        params={"eval_type": "reply_generate", "run_id": run_id},
    )
    assert report_resp.status_code == 200
    report_payload = report_resp.json()["data"]
    assert report_payload["run_id"] == run_id
    assert "intent_accuracy" in report_payload["metrics"]


def test_query_report_not_found() -> None:
    report_resp = client.get("/api/v1/ai/eval/report", params={"eval_type": "not_exists"})
    assert report_resp.status_code == 404
    assert report_resp.json()["error"]["code"] == "not_found"

