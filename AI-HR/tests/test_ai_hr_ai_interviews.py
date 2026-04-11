from __future__ import annotations

import time
import types
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_hr.core.config import get_settings
from ai_hr.domain.constants import InterviewStage
from ai_hr.schemas.ai_interviews import AIInterviewSessionStartRequest

from ai_hr.db.base import Base
from ai_hr.db.session import get_db_session
from ai_hr.main import app
from ai_hr.repositories.ai_interviews import AIInterviewSessionRepository
from ai_hr.repositories.ai_runtime import AIRuntimeRepository
from ai_hr.repositories.candidates import CandidateRepository
from ai_hr.repositories.events import EventRepository
from ai_hr.repositories.interviews import InterviewRepository
from ai_hr.repositories.jobs import JobRepository
from ai_hr.services.ai_interviews import AIInterviewService, get_ai_interview_service
from ai_hr.services.interview_runtime.memory_store import MemoryInterviewRuntimeStore


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
            "title": "AI Interview Backend Engineer",
            "department": "Engineering",
            "city": "Shanghai",
            "salary_range": "30k-45k",
            "requirements": "Python FastAPI",
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
                    "name": "AI Candidate",
                    "source_channel": "boss",
                    "external_candidate_id": "cand-ai-intv-1",
                    "resume_text": "Python, FastAPI, distributed systems",
                    "raw_profile": {"skills": ["Python", "FastAPI"]},
                }
            ]
        },
    )
    assert resp.status_code == 201
    return resp.json()["data"]["candidates"][0]["id"]


def test_create_ai_interview_session_success() -> None:
    job_id = _create_job()
    candidate_id = _create_candidate()

    resp = client.post(
        "/api/v1/ai/interviews/sessions",
        json={
            "candidate_id": candidate_id,
            "job_id": job_id,
            "channel": "self_hosted_rtc",
            "note": "棣栬疆 AI 璇煶闈㈣瘯",
            "payload": {"source": "auto_schedule"},
        },
    )
    assert resp.status_code == 201
    data = resp.json()["data"]["session"]
    assert data["status"] == "created"
    assert data["candidate_id"] == candidate_id
    assert data["job_id"] == job_id
    assert data["rtc_room_id"].startswith("ai-intv-")
    assert data["join_url"].startswith("/ai-interview/session/")
    assert "token=" in data["join_url"]
    assert data["rtc"]["room_id"] == data["rtc_room_id"]
    assert data["rtc"]["channel_name"] == data["rtc_room_id"]
    assert data["ten"]["room_id"] == data["rtc_room_id"]


def test_create_ai_interview_session_invalid_candidate() -> None:
    job_id = _create_job()

    resp = client.post(
        "/api/v1/ai/interviews/sessions",
        json={
            "candidate_id": "not-exists-candidate",
            "job_id": job_id,
        },
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def _create_ai_session(job_id: str, candidate_id: str) -> str:
    resp = client.post(
        "/api/v1/ai/interviews/sessions",
        json={
            "candidate_id": candidate_id,
            "job_id": job_id,
        },
    )
    assert resp.status_code == 201
    return resp.json()["data"]["session"]["id"]


def test_start_and_finish_ai_interview_session() -> None:
    job_id = _create_job()
    candidate_id = _create_candidate()
    session_id = _create_ai_session(job_id, candidate_id)

    start_resp = client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/start",
        json={"operator": "hr_user"},
    )
    assert start_resp.status_code == 200
    started = start_resp.json()["data"]
    assert started["status"] == "in_progress"

    finish_resp = client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/finish",
        json={"result_status": "completed", "operator": "hr_user"},
    )
    assert finish_resp.status_code == 200
    finished = finish_resp.json()["data"]
    assert finished["status"] == "completed"
    assert finished["ended_at"] is not None


def test_create_session_should_not_prepare_ten_property_before_start() -> None:
    job_id = _create_job()
    candidate_id = _create_candidate()
    session_provider = app.dependency_overrides.get(get_db_session, override_get_db_session)
    session_gen = session_provider()
    db = next(session_gen)
    try:
        service = AIInterviewService(
            session_repository=AIInterviewSessionRepository(db),
            runtime_repository=AIRuntimeRepository(db),
            candidate_repository=CandidateRepository(db),
            job_repository=JobRepository(db),
            interview_repository=InterviewRepository(db),
            event_repository=EventRepository(db),
            rtc_gateway=MagicMock(),
            asr_provider=MagicMock(),
            tts_provider=MagicMock(),
            llm_client=MagicMock(),
            orchestrator=MagicMock(),
            runtime_store=MemoryInterviewRuntimeStore(),
            ten_runtime_manager=MagicMock(),
        )
        service._build_rtc_payload = lambda rtc_info: {
            "rtc_vendor": "mock",
            "rtc_channel_name": "test-room",
            "rtc_app_id": "test-app",
            "rtc_uid": "1001",
        }
        service._rtc_gateway.create_room.return_value = types.SimpleNamespace(
            room_id="ai-intv-test",
            join_token="join-token",
        )
        created = service.create_session(
            payload=types.SimpleNamespace(
                candidate_id=candidate_id,
                job_id=job_id,
                channel="api",
                language="zh-CN",
                note=None,
                payload={},
            )
        )
    finally:
        session_gen.close()

    session_payload = created
    assert session_payload["ten"]["launch_status"] in {"pending_start", "disabled"}
    assert session_payload["ten"]["property_file"] in {None, ""}


def test_invalid_state_transition_should_fail() -> None:
    job_id = _create_job()
    candidate_id = _create_candidate()
    session_id = _create_ai_session(job_id, candidate_id)

    finish_resp = client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/finish",
        json={"result_status": "completed"},
    )
    assert finish_resp.status_code == 400
    assert finish_resp.json()["error"]["code"] == "domain_error"


def test_event_append_should_deduplicate_by_event_id() -> None:
    job_id = _create_job()
    candidate_id = _create_candidate()
    session_id = _create_ai_session(job_id, candidate_id)

    start_resp = client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/start",
        json={},
    )
    assert start_resp.status_code == 200

    first_event = client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/events",
        json={
            "event_id": "evt-1",
            "speaker": "candidate",
            "transcript": "我在上一份工作中负责服务稳定性建设。",
            "confidence": 0.88,
            "policy_flags": [],
        },
    )
    assert first_event.status_code == 200
    assert first_event.json()["data"]["accepted"] is True
    assert first_event.json()["data"]["deduplicated"] is False

    duplicate_event = client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/events",
        json={
            "event_id": "evt-1",
            "speaker": "candidate",
            "transcript": "閲嶅浜嬩欢",
            "confidence": 0.70,
        },
    )
    assert duplicate_event.status_code == 200
    assert duplicate_event.json()["data"]["accepted"] is False
    assert duplicate_event.json()["data"]["deduplicated"] is True


def test_handoff_should_mark_session_failed() -> None:
    job_id = _create_job()
    candidate_id = _create_candidate()
    session_id = _create_ai_session(job_id, candidate_id)

    start_resp = client.post(f"/api/v1/ai/interviews/sessions/{session_id}/start", json={})
    assert start_resp.status_code == 200

    handoff_resp = client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/handoff",
        json={
            "reason": "low_confidence_streak",
            "trigger_flags": ["low_confidence"],
            "operator": "system",
        },
    )
    assert handoff_resp.status_code == 200
    payload = handoff_resp.json()["data"]
    assert payload["handoff_id"]
    assert payload["session"]["status"] == "failed"


def test_generate_question_set_and_version_increment() -> None:
    job_id = _create_job()
    candidate_id = _create_candidate()
    session_id = _create_ai_session(job_id, candidate_id)

    first_resp = client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/question-set/generate",
        json={"question_count": 5},
    )
    assert first_resp.status_code == 200
    first = first_resp.json()["data"]
    assert first["version"] == 1
    assert first["question_count"] == 5
    assert len(first["questions"]) == 5
    assert set(first["questions"][0].keys()) == {"question", "dimension", "expected_signal", "followup_condition"}

    second_resp = client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/question-set/generate",
        json={"question_count": 3},
    )
    assert second_resp.status_code == 200
    second = second_resp.json()["data"]
    assert second["version"] == 2
    assert second["question_count"] == 3


def test_generate_question_set_not_found() -> None:
    resp = client.post(
        "/api/v1/ai/interviews/sessions/not-found-session/question-set/generate",
        json={"question_count": 3},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_prebuild_question_pack_should_write_to_runtime_store() -> None:
    job_id = _create_job()
    candidate_id = _create_candidate()
    resp = client.post(
        "/api/v1/ai/interviews/question-packs/prebuild",
        json={
            "candidate_id": candidate_id,
            "job_id": job_id,
            "language": "zh-CN",
            "question_count": 6,
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert isinstance(data["cache_key"], str) and len(data["cache_key"]) > 0
    assert 1 <= data["question_count"] <= 6
    assert data["expires_in_seconds"] > 0


def test_prebuild_question_pack_should_be_reusable_on_session_start() -> None:
    job_id = _create_job()
    candidate_id = _create_candidate()
    prebuild_resp = client.post(
        "/api/v1/ai/interviews/question-packs/prebuild",
        json={
            "candidate_id": candidate_id,
            "job_id": job_id,
            "language": "zh-CN",
            "question_count": 4,
        },
    )
    assert prebuild_resp.status_code == 200
    session_id = _create_ai_session(job_id, candidate_id)
    start_resp = client.post(f"/api/v1/ai/interviews/sessions/{session_id}/start", json={})
    assert start_resp.status_code == 200
    payload = start_resp.json()["data"]["payload"]
    assert payload.get("prebuilt_pack_hit") is True
    assert int(payload.get("question_pack_version") or 0) >= 1


def test_start_session_should_refresh_latest_question_pack_and_reset_runtime_state() -> None:
    job_id = _create_job()
    candidate_id = _create_candidate()

    session_provider = app.dependency_overrides.get(get_db_session, override_get_db_session)
    session_gen = session_provider()
    db = next(session_gen)
    try:
        service = AIInterviewService(
            session_repository=AIInterviewSessionRepository(db),
            runtime_repository=AIRuntimeRepository(db),
            candidate_repository=CandidateRepository(db),
            job_repository=JobRepository(db),
            interview_repository=InterviewRepository(db),
            event_repository=EventRepository(db),
            rtc_gateway=MagicMock(),
            asr_provider=MagicMock(),
            tts_provider=MagicMock(),
            llm_client=MagicMock(),
            orchestrator=MagicMock(),
            runtime_store=MemoryInterviewRuntimeStore(),
            ten_runtime_manager=MagicMock(),
        )
        service._prepare_ten_runtime = lambda entity: {}
        service._maybe_auto_launch_ten = lambda entity: entity
        entity = service._session_repository.create(
            candidate_id=candidate_id,
            job_id=job_id,
            channel="api",
            language="zh-CN",
            rtc_room_id="test-room",
            join_token="test-token",
            payload={"interview_stage": InterviewStage.OPENING},
        )
        session_id = entity.id
        service._session_repository.create_question_set(
            session_id=session_id,
            version=1,
            source="test_old",
            questions=[
                {"idx": 1, "stage": "S2", "question": "old-intro"},
                {"idx": 14, "stage": "S3", "question": "old-focus-module"},
            ],
        )
        service._runtime_store.save_question_pack(
            session_id=session_id,
            version=1,
            question_pack={
                "session_id": session_id,
                "version": 1,
                "source": "test_old",
                "question_count": 2,
                "questions": [
                    {"idx": 1, "stage": "S2", "question": "old-intro"},
                    {"idx": 14, "stage": "S3", "question": "old-focus-module"},
                ],
            },
            ttl_seconds=3600,
        )
        service._runtime_store.init_session_state(
            session_id=session_id,
            state={
                "interview_stage": "S4",
                "active_question_index": 9,
                "current_question_id": "old-q14",
                "question_statuses": ["completed", "completed"],
            },
            ttl_seconds=3600,
        )
        service._session_repository.create_question_set(
            session_id=session_id,
            version=2,
            source="test_new",
            questions=[
                {"idx": 1, "stage": "S2", "question": "new-intro"},
                {"idx": 2, "stage": "S3", "question": "new-s3-q1"},
                {"idx": 3, "stage": "S3", "question": "new-s3-q2"},
            ],
        )
        started = service.start_session(session_id, AIInterviewSessionStartRequest())
    finally:
        session_gen.close()

    payload = started["payload"]
    assert int(payload.get("question_pack_version") or 0) == 2
    assert payload.get("question_pack_source") == "test_new"
    assert isinstance(payload.get("question_pack"), dict)
    assert [item.get("question") for item in payload["question_pack"].get("questions", [])] == [
        "new-intro",
        "new-s3-q1",
        "new-s3-q2",
    ]

    session_gen = session_provider()
    db = next(session_gen)
    try:
        pack = service._runtime_store.get_question_pack(session_id=session_id)
        state = service._runtime_store.get_session_state(session_id=session_id)
    finally:
        session_gen.close()

    assert pack is not None
    assert int(pack.get("version") or 0) == 2
    assert pack.get("source") == "test_new"
    assert [item.get("question") for item in pack.get("questions", [])] == [
        "new-intro",
        "new-s3-q1",
        "new-s3-q2",
    ]
    assert state is not None
    assert state.get("interview_stage") == "S1"
    assert int(state.get("active_question_index") or 0) == 0
    assert str(state.get("current_question_id") or "") == ""


def test_start_session_should_auto_generate_question_pack_when_missing() -> None:
    job_id = _create_job()
    candidate_id = _create_candidate()

    session_provider = app.dependency_overrides.get(get_db_session, override_get_db_session)
    session_gen = session_provider()
    db = next(session_gen)
    try:
        service = AIInterviewService(
            session_repository=AIInterviewSessionRepository(db),
            runtime_repository=AIRuntimeRepository(db),
            candidate_repository=CandidateRepository(db),
            job_repository=JobRepository(db),
            interview_repository=InterviewRepository(db),
            event_repository=EventRepository(db),
            rtc_gateway=MagicMock(),
            asr_provider=MagicMock(),
            tts_provider=MagicMock(),
            llm_client=MagicMock(),
            orchestrator=MagicMock(),
            runtime_store=MemoryInterviewRuntimeStore(),
            ten_runtime_manager=MagicMock(),
        )
        service._prepare_ten_runtime = lambda entity: {}
        service._maybe_auto_launch_ten = lambda entity: entity
        entity = service._session_repository.create(
            candidate_id=candidate_id,
            job_id=job_id,
            channel="api",
            language="zh-CN",
            rtc_room_id="test-room-2",
            join_token="test-token-2",
            payload={"interview_stage": InterviewStage.OPENING},
        )
        started = service.start_session(entity.id, AIInterviewSessionStartRequest())
        pack = service._runtime_store.get_question_pack(session_id=entity.id)
        state = service._runtime_store.get_session_state(session_id=entity.id)
    finally:
        session_gen.close()

    assert int(started["payload"].get("question_count") or 0) > 0
    assert isinstance(started["payload"].get("question_pack"), dict)
    assert pack is not None
    assert int(pack.get("question_count") or 0) > 0
    assert isinstance(pack.get("questions"), list) and len(pack["questions"]) > 0
    assert state is not None
    assert state.get("interview_stage") == "S1"


def test_integration_flow_create_start_finish_and_report() -> None:
    """QA-005: 端到端集成流程测试。"""
    job_id = _create_job()
    candidate_id = _create_candidate()
    session_id = _create_ai_session(job_id, candidate_id)

    assert client.post(f"/api/v1/ai/interviews/sessions/{session_id}/start", json={}).status_code == 200
    assert (
        client.post(
            f"/api/v1/ai/interviews/sessions/{session_id}/events",
            json={
                "event_id": "evt-int-1",
                "speaker": "candidate",
                "transcript": "我负责过高并发服务治理和容量规划。",
                "confidence": 0.93,
                "audio_uri": "oss://bucket/audio-1.wav",
            },
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/ai/interviews/sessions/{session_id}/finish",
            json={"result_status": "completed", "operator": "hr_user"},
        ).status_code
        == 200
    )
    report_resp = client.get(f"/api/v1/ai/interviews/sessions/{session_id}/report")
    assert report_resp.status_code == 200
    report = report_resp.json()["data"]
    assert report["session_id"] == session_id
    assert report["report_version"] >= 1
    assert report["run_id"].startswith("run_")
    assert isinstance(report["dimension_scores"], dict)


def test_report_run_id_should_be_reproducible_and_replay_queryable() -> None:
    """BE-013 + BE-017: run_id 可复算与 turn 级回放查询。"""
    job_id = _create_job()
    candidate_id = _create_candidate()
    session_id = _create_ai_session(job_id, candidate_id)

    assert client.post(f"/api/v1/ai/interviews/sessions/{session_id}/start", json={}).status_code == 200
    assert (
        client.post(
            f"/api/v1/ai/interviews/sessions/{session_id}/events",
            json={
                "event_id": "evt-replay-1",
                "speaker": "candidate",
                "transcript": "I led a migration from monolith to services.",
                "confidence": 0.91,
                "audio_uri": "oss://bucket/audio-replay-1.wav",
            },
        ).status_code
        == 200
    )
    first = client.get(f"/api/v1/ai/interviews/sessions/{session_id}/report")
    assert first.status_code == 200
    run_id = first.json()["data"]["run_id"]

    second = client.get(f"/api/v1/ai/interviews/sessions/{session_id}/report", params={"run_id": run_id})
    assert second.status_code == 200
    assert second.json()["data"]["run_id"] == run_id

    replay_resp = client.get(
        f"/api/v1/ai/interviews/sessions/{session_id}/replay",
        params={"limit": 10, "offset": 0},
    )
    assert replay_resp.status_code == 200
    replay = replay_resp.json()["data"]
    assert replay["session_id"] == session_id
    assert replay["total_turns"] >= 1
    assert replay["items"][0]["turn_no"] >= 1
    assert "transcript" in replay["items"][0]


def test_stage_machine_and_followup_should_be_observable() -> None:
    job_id = _create_job()
    candidate_id = _create_candidate()
    session_id = _create_ai_session(job_id, candidate_id)
    assert client.post(f"/api/v1/ai/interviews/sessions/{session_id}/start", json={}).status_code == 200

    first = client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/events",
        json={
            "event_id": "evt-stage-1",
            "speaker": "candidate",
            "transcript": "简要回答",
            "confidence": 0.55,
        },
    )
    assert first.status_code == 200
    payload = first.json()["data"]
    assert payload["interview_stage"] == "intro"
    assert payload["followup_question"] is not None
    assert payload["decision_reason"] in {"low_confidence_but_within_threshold", "confidence_passed"}

    second = client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/events",
        json={
            "event_id": "evt-stage-2",
            "speaker": "candidate",
            "transcript": "仍然低置信回答",
            "confidence": 0.52,
        },
    )
    assert second.status_code == 200
    assert second.json()["data"]["action"] == "handoff"


def test_sensitive_content_should_block_and_stop_followup() -> None:
    job_id = _create_job()
    candidate_id = _create_candidate()
    session_id = _create_ai_session(job_id, candidate_id)
    assert client.post(f"/api/v1/ai/interviews/sessions/{session_id}/start", json={}).status_code == 200
    runtime_flag_resp = client.put(
        "/api/v1/ai/runtime/feature-flags/ai_interview_runtime",
        json={"enabled": True, "rollout_percent": 100, "fallback_mode": "llm_first"},
    )
    assert runtime_flag_resp.status_code == 200
    resp = client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/events",
        json={
            "event_id": "evt-block-1",
            "speaker": "candidate",
            "transcript": "\u6211\u53ef\u4ee5\u63d0\u4f9b\u8eab\u4efd\u8bc1\u548c\u94f6\u884c\u5361\u4fe1\u606f",
            "confidence": 0.95,
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["action"] == "blocked"
    assert data["followup_question"] is None
    assert "sensitive:" in data["policy_flags"][0]


def test_multilingual_question_generation_and_model_route() -> None:
    job_id = _create_job()
    candidate_id = _create_candidate()
    create_resp = client.post(
        "/api/v1/ai/interviews/sessions",
        json={
            "candidate_id": candidate_id,
            "job_id": job_id,
            "language": "en-US",
            "payload": {"model_route_policy": "cost_first"},
        },
    )
    assert create_resp.status_code == 201
    session_id = create_resp.json()["data"]["session"]["id"]
    assert create_resp.json()["data"]["session"]["language"] == "en-US"

    q_resp = client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/question-set/generate",
        json={"question_count": 4},
    )
    assert q_resp.status_code == 200
    questions = q_resp.json()["data"]["questions"]
    assert questions[0]["question"].startswith("Please")

    assert client.post(f"/api/v1/ai/interviews/sessions/{session_id}/start", json={}).status_code == 200
    event_resp = client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/events",
        json={
            "event_id": "evt-route-1",
            "speaker": "candidate",
            "transcript": "I designed a resilient API platform.",
            "confidence": 0.9,
        },
    )
    assert event_resp.status_code == 200
    assert event_resp.json()["data"]["model_route"] == "cost_optimized"


def test_metrics_endpoint_should_return_alert_dimensions() -> None:
    job_id = _create_job()
    candidate_id = _create_candidate()
    session_id = _create_ai_session(job_id, candidate_id)
    question_resp = client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/question-set/generate",
        json={"question_count": 5},
    )
    assert question_resp.status_code == 200
    assert client.post(f"/api/v1/ai/interviews/sessions/{session_id}/start", json={}).status_code == 200
    for idx in range(5):
        assert (
            client.post(
                f"/api/v1/ai/interviews/sessions/{session_id}/events",
                json={
                    "event_id": f"evt-lat-{idx}",
                    "speaker": "candidate",
                    "transcript": f"鍥炵瓟-{idx}",
                    "confidence": 0.85,
                    "latency_ms": 1900 + idx,
                },
            ).status_code
            == 200
        )
    metric_resp = client.get("/api/v1/ai/interviews/metrics", params={"window_minutes": 120, "min_samples": 1})
    assert metric_resp.status_code == 200
    metrics = metric_resp.json()["data"]
    assert "handoff_rate" in metrics
    assert "blocked_rate" in metrics
    assert "latency_p95_ms" in metrics
    assert "llm_first_token_p95_ms" in metrics
    assert "tts_first_packet_p95_ms" in metrics
    assert "followup_repeat_rate" in metrics
    assert "prefetch_hit_rate" in metrics
    assert "question_completion_rate" in metrics
    assert metrics["question_completion_rate"] > 0.0
    assert metrics["question_completion_rate"] <= 1.0


def test_runtime_flag_switch_should_take_effect_immediately() -> None:
    job_id = _create_job()
    candidate_id = _create_candidate()
    session_id = _create_ai_session(job_id, candidate_id)
    assert client.post(f"/api/v1/ai/interviews/sessions/{session_id}/start", json={}).status_code == 200

    put_flag = client.put(
        "/api/v1/ai/runtime/feature-flags/ai_interview_runtime",
        json={
            "tenant_id": None,
            "enabled": False,
            "rollout_percent": 0,
            "fallback_mode": "rule_only",
        },
    )
    assert put_flag.status_code == 200

    event_resp = client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/events",
        json={
            "event_id": "evt-runtime-1",
            "speaker": "candidate",
            "transcript": "短回答",
            "confidence": 0.9,
        },
    )
    assert event_resp.status_code == 200
    assert event_resp.json()["data"]["runtime_mode"] == "rule_only"


def test_rtc_join_and_reconnect_should_succeed() -> None:
    job_id = _create_job()
    candidate_id = _create_candidate()
    session_id = _create_ai_session(job_id, candidate_id)
    assert client.post(f"/api/v1/ai/interviews/sessions/{session_id}/start", json={}).status_code == 200

    join_resp = client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/rtc/join",
        json={"candidate_id": candidate_id, "client_id": "web-1"},
    )
    assert join_resp.status_code == 200
    join_payload = join_resp.json()["data"]
    assert join_payload["reconnectable"] is True
    assert join_payload["room_id"].startswith("ai-intv-")
    assert join_payload["channel_name"] == join_payload["room_id"]
    assert join_payload["provider"] in {"mock", "livekit", "agora"}

    reconnect_resp = client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/rtc/reconnect",
        json={"client_id": "web-1", "reason": "network_jitter"},
    )
    assert reconnect_resp.status_code == 200
    reconnect_payload = reconnect_resp.json()["data"]
    assert reconnect_payload["reconnected"] is True
    assert reconnect_payload["reconnect_count"] >= 1


def test_ten_runtime_config_endpoint_should_reflect_session_state() -> None:
    job_id = _create_job()
    candidate_id = _create_candidate()
    session_id = _create_ai_session(job_id, candidate_id)
    assert client.post(f"/api/v1/ai/interviews/sessions/{session_id}/start", json={}).status_code == 200

    runtime_resp = client.get(f"/api/v1/ai/interviews/sessions/{session_id}/ten/runtime-config")
    assert runtime_resp.status_code == 200
    runtime_payload = runtime_resp.json()["data"]
    assert runtime_payload["session_id"] == session_id
    assert runtime_payload["room_id"].startswith("ai-intv-")
    assert runtime_payload["provider"] in {"mock", "livekit", "agora"}


def test_finished_session_should_reject_realtime_entrypoints() -> None:
    job_id = _create_job()
    candidate_id = _create_candidate()
    session_id = _create_ai_session(job_id, candidate_id)

    assert client.post(f"/api/v1/ai/interviews/sessions/{session_id}/start", json={}).status_code == 200
    assert (
        client.post(
            f"/api/v1/ai/interviews/sessions/{session_id}/finish",
            json={"result_status": "completed", "operator": "hr_user"},
        ).status_code
        == 200
    )

    join_resp = client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/rtc/join",
        json={"candidate_id": candidate_id, "client_id": "web-finished"},
    )
    assert join_resp.status_code == 400
    assert join_resp.json()["error"]["code"] == "domain_error"

    runtime_resp = client.get(f"/api/v1/ai/interviews/sessions/{session_id}/ten/runtime-config")
    assert runtime_resp.status_code == 400
    assert runtime_resp.json()["error"]["code"] == "domain_error"

    launch_resp = client.post(f"/api/v1/ai/interviews/sessions/{session_id}/ten/launch")
    assert launch_resp.status_code == 400
    assert launch_resp.json()["error"]["code"] == "domain_error"


def test_rtc_asr_and_tts_stream_should_work() -> None:
    job_id = _create_job()
    candidate_id = _create_candidate()
    session_id = _create_ai_session(job_id, candidate_id)

    asr_resp = client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/rtc/asr/stream",
        json={"seq": 1, "text_hint": "我负责过高并发系统治理", "confidence": 0.92, "latency_ms": 620},
    )
    assert asr_resp.status_code == 200
    asr_payload = asr_resp.json()["data"]
    assert asr_payload["transcript"] == "我负责过高并发系统治理"
    assert asr_payload["p95_target_met"] is True

    tts_resp = client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/rtc/tts/stream",
        json={"text": "请详细介绍你在上一家公司主导的系统改造项目。", "voice": "female_a", "chunk_size": 10},
    )
    assert tts_resp.status_code == 200
    tts_payload = tts_resp.json()["data"]
    assert tts_payload["voice"] == "female_a"
    assert len(tts_payload["chunks"]) >= 1
    assert tts_payload["audio_uris"][0].startswith("mock://tts/")


def test_llm_question_generation_and_followup_when_feature_enabled() -> None:
    job_id = _create_job()
    candidate_id = _create_candidate()
    session_id = _create_ai_session(job_id, candidate_id)

    flag_resp = client.put(
        "/api/v1/ai/runtime/feature-flags/ai_interview_llm",
        json={"enabled": True, "rollout_percent": 100, "fallback_mode": "llm_first"},
    )
    assert flag_resp.status_code == 200

    q_resp = client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/question-set/generate",
        json={"question_count": 2},
    )
    assert q_resp.status_code == 200
    first_question = q_resp.json()["data"]["questions"][0]["question"]
    assert isinstance(first_question, str) and len(first_question) > 0

    assert client.post(f"/api/v1/ai/interviews/sessions/{session_id}/start", json={}).status_code == 200
    event_resp = client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/events",
        json={
            "event_id": "evt-llm-followup-1",
            "speaker": "candidate",
            "transcript": "我负责系统优化",
            "confidence": 0.9,
        },
    )
    assert event_resp.status_code == 200
    payload = event_resp.json()["data"]
    followup = payload["followup_question"]
    assert isinstance(followup, str) and len(followup) > 0
    assert payload["degradation_mode"] in {None, "llm_to_rule", "tts_to_text_only", "llm_to_rule+tts_to_text_only"}


def test_followup_prompt_should_include_current_question_context(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    job_id = _create_job()
    candidate_id = _create_candidate()
    session_id = _create_ai_session(job_id, candidate_id)
    captured: dict[str, str] = {}

    def _fake_invoke(self, context, on_text_delta=None, write_observability=True):  # noqa: ANN001
        captured["prompt"] = context.prompt
        return types.SimpleNamespace(content={"text": "请补充量化指标和个人贡献比例。"})

    monkeypatch.setattr("ai_hr.services.llm.client.LLMClient.invoke", _fake_invoke)
    flag_resp = client.put(
        "/api/v1/ai/runtime/feature-flags/ai_interview_llm",
        json={"enabled": True, "rollout_percent": 100, "fallback_mode": "llm_first"},
    )
    assert flag_resp.status_code == 200
    q_resp = client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/question-set/generate",
        json={"question_count": 2},
    )
    assert q_resp.status_code == 200
    first_question = q_resp.json()["data"]["questions"][0]["question"]
    assert client.post(f"/api/v1/ai/interviews/sessions/{session_id}/start", json={}).status_code == 200
    event_resp = client.post(
        f"/api/v1/ai/interviews/sessions/{session_id}/events",
        json={
            "event_id": "evt-followup-prompt-1",
            "speaker": "candidate",
            "transcript": "我做了系统优化",
            "confidence": 0.9,
        },
    )
    assert event_resp.status_code == 200
    prompt = captured.get("prompt", "")
    assert "当前题目" in prompt
    assert first_question[:8] in prompt


def test_partial_prefetch_should_use_session_language_and_stage() -> None:
    job_id = _create_job()
    candidate_id = _create_candidate()
    create_resp = client.post(
        "/api/v1/ai/interviews/sessions",
        json={"candidate_id": candidate_id, "job_id": job_id, "language": "en-US"},
    )
    assert create_resp.status_code == 201
    session_id = create_resp.json()["data"]["session"]["id"]
    session_provider = app.dependency_overrides.get(get_db_session, override_get_db_session)
    session_gen = session_provider()
    db = next(session_gen)
    try:
        service = get_ai_interview_service(db)
        captured: dict[str, str] = {}

        def _fake_worker(self, **kwargs):  # noqa: ANN001
            captured["stage"] = str(kwargs.get("stage"))
            captured["language"] = str(kwargs.get("language"))

        service._run_partial_prefetch_worker = types.MethodType(_fake_worker, service)  # type: ignore[method-assign]
        settings = get_settings()
        old_partial = settings.ai_interview_duplex_partial_trigger_enabled
        old_llm = settings.ai_interview_llm_enabled
        try:
            settings.ai_interview_duplex_partial_trigger_enabled = True
            settings.ai_interview_llm_enabled = True
            service._maybe_prefetch_partial_followup(
                session_id=session_id,
                seq=1,
                transcript="I improved API latency and reduced p95 by 40 percent.",
                confidence=0.91,
            )
            time.sleep(0.1)
        finally:
            settings.ai_interview_duplex_partial_trigger_enabled = old_partial
            settings.ai_interview_llm_enabled = old_llm
    finally:
        session_gen.close()
    assert captured.get("language") == "en-US"
    assert captured.get("stage") in {"intro", "verification", "core_questions", "deep_dive", "candidate_questions"}


def test_rtc_audio_subscribe_should_work_when_feature_enabled() -> None:
    job_id = _create_job()
    candidate_id = _create_candidate()
    session_id = _create_ai_session(job_id, candidate_id)

    settings = get_settings()
    old_enabled = settings.ai_interview_rtc_audio_subscribe_enabled
    old_auto = settings.ai_interview_rtc_audio_subscribe_auto
    old_track_ids = settings.ai_interview_rtc_audio_track_ids
    try:
        settings.ai_interview_rtc_audio_subscribe_enabled = True
        settings.ai_interview_rtc_audio_subscribe_auto = True
        settings.ai_interview_rtc_audio_track_ids = None
        subscribe_resp = client.post(
            f"/api/v1/ai/interviews/sessions/{session_id}/rtc/audio/subscribe",
            json={"candidate_id": candidate_id, "client_id": "web-rtc-1"},
        )
    finally:
        settings.ai_interview_rtc_audio_subscribe_enabled = old_enabled
        settings.ai_interview_rtc_audio_subscribe_auto = old_auto
        settings.ai_interview_rtc_audio_track_ids = old_track_ids

    assert subscribe_resp.status_code == 200
    payload = subscribe_resp.json()["data"]
    assert payload["feature_enabled"] is True
    assert payload["subscribed"] is True
    assert payload["mode"] == "mock_auto"
    assert payload["participant_identity"] == f"{candidate_id}:web-rtc-1"
    assert len(payload["track_sids"]) >= 1


def test_rtc_audio_subscribe_should_be_disabled_by_feature_flag() -> None:
    job_id = _create_job()
    candidate_id = _create_candidate()
    session_id = _create_ai_session(job_id, candidate_id)

    settings = get_settings()
    old_enabled = settings.ai_interview_rtc_audio_subscribe_enabled
    try:
        settings.ai_interview_rtc_audio_subscribe_enabled = False
        subscribe_resp = client.post(
            f"/api/v1/ai/interviews/sessions/{session_id}/rtc/audio/subscribe",
            json={"candidate_id": candidate_id, "client_id": "web-rtc-2"},
        )
    finally:
        settings.ai_interview_rtc_audio_subscribe_enabled = old_enabled

    assert subscribe_resp.status_code == 200
    payload = subscribe_resp.json()["data"]
    assert payload["feature_enabled"] is False
    assert payload["subscribed"] is False
    assert payload["mode"] == "disabled"
    assert payload["track_sids"] == []

