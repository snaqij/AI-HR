from __future__ import annotations

from datetime import UTC, datetime, timedelta
import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_hr.db.base import Base
from ai_hr.db.models import AIInterviewSession, AIInterviewTurn, Candidate, Event, Job
from ai_hr.services.ai_lifecycle import AIInterviewLifecycleService


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
Base.metadata.create_all(bind=engine)


def _seed_data(session: Session) -> tuple[str, str]:
    now = datetime.now(UTC).replace(tzinfo=None)
    suffix = uuid.uuid4().hex[:8]
    job = Job(
        id=f"job-{suffix}",
        title="Lifecycle Job",
        city="Shanghai",
        requirements="Python",
        status="draft",
    )
    candidate = Candidate(
        id=f"cand-{suffix}",
        name="Lifecycle Candidate",
        source_channel="boss",
        external_candidate_id=f"cand-ext-{suffix}",
        raw_profile={},
        score_dimensions={},
    )
    session.add_all([job, candidate])
    session.commit()

    interview_session = AIInterviewSession(
        candidate_id=candidate.id,
        job_id=job.id,
        status="in_progress",
        channel="self_hosted_rtc",
        language="zh-CN",
        rtc_room_id=f"room-{suffix}",
        join_token=f"token-{suffix}",
        payload={},
    )
    session.add(interview_session)
    session.commit()

    expired_turn = AIInterviewTurn(
        session_id=interview_session.id,
        turn_no=1,
        speaker="candidate",
        transcript="expired transcript",
        audio_uri="oss://expired.wav",
        transcript_expires_at=now - timedelta(days=400),
        audio_expires_at=now - timedelta(days=400),
        confidence=0.8,
        latency_ms=600,
        policy_flags=[],
        payload={},
    )
    active_turn = AIInterviewTurn(
        session_id=interview_session.id,
        turn_no=2,
        speaker="candidate",
        transcript="active transcript",
        audio_uri="oss://active.wav",
        transcript_expires_at=now + timedelta(days=10),
        audio_expires_at=now + timedelta(days=10),
        confidence=0.8,
        latency_ms=600,
        policy_flags=[],
        payload={},
    )
    session.add_all([expired_turn, active_turn])

    old_event = Event(
        event_type="ai_interview.rtc.join",
        entity_type="ai_interview_session",
        entity_id=interview_session.id,
        status="success",
        occurred_at=now - timedelta(days=500),
        payload={},
    )
    new_event = Event(
        event_type="ai_interview.rtc.join",
        entity_type="ai_interview_session",
        entity_id=interview_session.id,
        status="success",
        occurred_at=now,
        payload={},
    )
    session.add_all([old_event, new_event])
    session.commit()
    return expired_turn.id, active_turn.id


def test_lifecycle_cleanup_dry_run_should_not_modify_data() -> None:
    with TestingSessionLocal() as session:
        _seed_data(session)
        service = AIInterviewLifecycleService(session)
        result = service.run_cleanup(dry_run=True, batch_size=100)
        assert result["audit_event_id"]
        assert result["transcript_candidates"] >= 1
        assert result["audio_candidates"] >= 1
        assert result["event_candidates"] >= 1

        turns = session.execute(select(AIInterviewTurn)).scalars().all()
        assert any(item.transcript == "expired transcript" for item in turns)
        assert any(item.audio_uri == "oss://expired.wav" for item in turns)
        lifecycle_events = (
            session.execute(select(Event).where(Event.event_type == "ai_interview.lifecycle.cleanup")).scalars().all()
        )
        assert len(lifecycle_events) >= 1
        assert lifecycle_events[-1].payload.get("dry_run") is True


def test_lifecycle_cleanup_should_clear_expired_fields_and_events() -> None:
    with TestingSessionLocal() as session:
        expired_turn_id, active_turn_id = _seed_data(session)
        service = AIInterviewLifecycleService(session)
        result = service.run_cleanup(dry_run=False, batch_size=100)
        assert result["audit_event_id"]
        assert result["transcript_cleared"] >= 1
        assert result["audio_cleared"] >= 1
        assert result["event_deleted"] >= 1

        expired_turn = session.execute(select(AIInterviewTurn).where(AIInterviewTurn.id == expired_turn_id)).scalar_one()
        active_turn = session.execute(select(AIInterviewTurn).where(AIInterviewTurn.id == active_turn_id)).scalar_one()
        assert expired_turn.transcript is None
        assert expired_turn.audio_uri is None
        assert active_turn.transcript == "active transcript"
        assert active_turn.audio_uri == "oss://active.wav"
        lifecycle_events = (
            session.execute(select(Event).where(Event.event_type == "ai_interview.lifecycle.cleanup")).scalars().all()
        )
        assert len(lifecycle_events) >= 1
        assert lifecycle_events[-1].payload.get("dry_run") is False
