from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_hr.db.base import Base
from ai_hr.db.session import get_db_session
from ai_hr.main import app
from ai_hr.repositories.ai_runtime import AIRuntimeRepository


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


def test_runtime_model_prompt_and_feature_flag_apis() -> None:
    model_resp = client.put(
        "/api/v1/ai/runtime/model-configs/resume_parse",
        json={
            "provider": "mock",
            "model_name": "resume-parse-runtime-mock",
            "temperature_milli": 150,
            "timeout_seconds": 10,
            "max_retries": 2,
            "is_active": True,
            "weight": 120,
        },
    )
    assert model_resp.status_code == 200
    assert model_resp.json()["data"]["model_name"] == "resume-parse-runtime-mock"

    model_get = client.get("/api/v1/ai/runtime/model-configs/resume_parse")
    assert model_get.status_code == 200
    assert model_get.json()["data"]["provider"] == "mock"

    prompt_resp = client.put(
        "/api/v1/ai/runtime/prompts/resume_parse",
        json={
            "version": "v1",
            "system_prompt": "system",
            "user_template": "resume: {resume_text}",
            "output_schema": {"type": "object"},
            "is_active": True,
            "created_by": "tester",
        },
    )
    assert prompt_resp.status_code == 200
    assert prompt_resp.json()["data"]["version"] == "v1"

    prompt_get = client.get("/api/v1/ai/runtime/prompts/resume_parse")
    assert prompt_get.status_code == 200
    assert prompt_get.json()["data"]["task_key"] == "resume_parse"

    prompt_resp_v2 = client.put(
        "/api/v1/ai/runtime/prompts/resume_parse",
        json={
            "version": "v2",
            "system_prompt": "system-v2",
            "user_template": "resume2: {resume_text}",
            "output_schema": {"type": "object"},
            "is_active": True,
            "created_by": "tester",
        },
    )
    assert prompt_resp_v2.status_code == 200
    assert prompt_resp_v2.json()["data"]["version"] == "v2"

    active_prompt = client.get("/api/v1/ai/runtime/prompts/resume_parse")
    assert active_prompt.status_code == 200
    assert active_prompt.json()["data"]["version"] == "v2"

    versions_resp = client.get("/api/v1/ai/runtime/prompts/resume_parse/versions")
    assert versions_resp.status_code == 200
    versions = versions_resp.json()["data"]
    assert len(versions) >= 2

    activate_resp = client.post("/api/v1/ai/runtime/prompts/resume_parse/versions/v1/activate")
    assert activate_resp.status_code == 200
    assert activate_resp.json()["data"]["version"] == "v1"
    assert activate_resp.json()["data"]["is_active"] is True

    rollback_prompt_resp = client.post("/api/v1/ai/runtime/prompts/resume_parse/rollback")
    assert rollback_prompt_resp.status_code == 200
    assert rollback_prompt_resp.json()["data"]["version"] == "v2"
    assert rollback_prompt_resp.json()["data"]["is_active"] is True

    flag_resp = client.put(
        "/api/v1/ai/runtime/feature-flags/ai_resume_llm",
        json={
            "tenant_id": "tenant-a",
            "job_id": "job-123",
            "enabled": True,
            "rollout_percent": 100,
            "fallback_mode": "llm_first",
        },
    )
    assert flag_resp.status_code == 200
    assert flag_resp.json()["data"]["enabled"] is True
    assert flag_resp.json()["data"]["job_id"] == "job-123"

    flag_get = client.get(
        "/api/v1/ai/runtime/feature-flags/ai_resume_llm",
        params={"tenant_id": "tenant-a", "job_id": "job-123"},
    )
    assert flag_get.status_code == 200
    assert flag_get.json()["data"]["fallback_mode"] == "llm_first"
    assert flag_get.json()["data"]["job_id"] == "job-123"


def test_runtime_rollback_switch_affects_resume_parse_path() -> None:
    import_resp = client.post(
        "/api/v1/candidates/import",
        json={
            "candidates": [
                {
                    "name": "Runtime Candidate",
                    "source_channel": "boss",
                    "external_candidate_id": "cand-runtime-1",
                    "resume_text": "5 years Python and FastAPI experience, bachelor degree.",
                    "raw_profile": {"skills": ["Python", "FastAPI"]},
                }
            ]
        },
    )
    assert import_resp.status_code == 201
    candidate_id = import_resp.json()["data"]["candidates"][0]["id"]

    enable_resp = client.put(
        "/api/v1/ai/runtime/feature-flags/ai_resume_llm",
        json={"enabled": True, "rollout_percent": 100, "fallback_mode": "llm_first"},
    )
    assert enable_resp.status_code == 200

    parse_with_llm = client.post("/api/v1/ai/resume/parse", json={"candidate_id": candidate_id})
    assert parse_with_llm.status_code == 200
    assert parse_with_llm.json()["data"]["profile"]["parser_version"] == "llm-v1"

    rollback_resp = client.post("/api/v1/ai/runtime/feature-flags/ai_resume_llm/rollback")
    assert rollback_resp.status_code == 200
    assert rollback_resp.json()["data"]["fallback_mode"] == "rule_only"
    assert rollback_resp.json()["data"]["enabled"] is False

    parse_after_rollback = client.post("/api/v1/ai/resume/parse", json={"candidate_id": candidate_id})
    assert parse_after_rollback.status_code == 200
    assert parse_after_rollback.json()["data"]["profile"]["parser_version"] == "heuristic-v1"


def test_runtime_feature_flag_resolution_should_prioritize_tenant_job_scope() -> None:
    with TestingSessionLocal() as session:
        repository = AIRuntimeRepository(session)
        repository.upsert_feature_flag(
            feature_key="ai_interview_llm",
            tenant_id=None,
            job_id=None,
            enabled=False,
            rollout_percent=0,
            fallback_mode="rule_only",
        )
        repository.upsert_feature_flag(
            feature_key="ai_interview_llm",
            tenant_id="tenant-a",
            job_id=None,
            enabled=False,
            rollout_percent=0,
            fallback_mode="rule_only",
        )
        repository.upsert_feature_flag(
            feature_key="ai_interview_llm",
            tenant_id="tenant-a",
            job_id="job-1",
            enabled=True,
            rollout_percent=100,
            fallback_mode="llm_first",
        )

        enabled_for_job_scope = repository.is_feature_enabled(
            feature_key="ai_interview_llm",
            tenant_id="tenant-a",
            job_id="job-1",
            default_enabled=False,
        )
        enabled_for_other_job = repository.is_feature_enabled(
            feature_key="ai_interview_llm",
            tenant_id="tenant-a",
            job_id="job-2",
            default_enabled=True,
        )
        enabled_without_tenant = repository.is_feature_enabled(
            feature_key="ai_interview_llm",
            tenant_id=None,
            job_id=None,
            default_enabled=True,
        )

        assert enabled_for_job_scope is True
        assert enabled_for_other_job is False
        assert enabled_without_tenant is False
