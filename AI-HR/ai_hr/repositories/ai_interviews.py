"""Repository helpers for AI interview sessions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..core.exceptions import InvalidStateError, ResourceNotFoundError
from ..db.models import (
    AIInterviewHandoff,
    AIInterviewInvitation,
    AIInterviewQuestionSet,
    AIInterviewReport,
    AIInterviewSession,
    AIInterviewTurn,
)


class AIInterviewSessionRepository:
    """Persistence layer for AI interview sessions and related records."""

    def __init__(self, session: Session):
        self._session = session

    def create(
        self,
        *,
        candidate_id: str,
        job_id: str,
        channel: str,
        language: str,
        rtc_room_id: str,
        join_token: str,
        note: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> AIInterviewSession:
        entity = AIInterviewSession(
            candidate_id=candidate_id,
            job_id=job_id,
            status="created",
            channel=channel,
            language=language,
            rtc_room_id=rtc_room_id,
            join_token=join_token,
            note=note,
            payload=payload or {},
        )
        self._session.add(entity)
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def get(self, session_id: str) -> AIInterviewSession:
        stmt = select(AIInterviewSession).where(AIInterviewSession.id == session_id)
        entity = self._session.execute(stmt).scalar_one_or_none()
        if entity is None:
            raise ResourceNotFoundError(f"AI interview session '{session_id}' was not found")
        return entity

    def get_by_room_id(self, room_id: str) -> AIInterviewSession | None:
        stmt = select(AIInterviewSession).where(AIInterviewSession.rtc_room_id == room_id)
        return self._session.execute(stmt).scalar_one_or_none()

    def update_status(
        self,
        session_id: str,
        *,
        status: str,
        note: str | None = None,
        payload_patch: dict[str, Any] | None = None,
    ) -> AIInterviewSession:
        entity = self.get(session_id)
        entity.status = status
        if note is not None:
            entity.note = note
        now = datetime.now(UTC).replace(tzinfo=None)
        if status == "in_progress":
            entity.started_at = entity.started_at or now
        if status in {"completed", "failed"}:
            entity.ended_at = now
        merged_payload = dict(entity.payload or {})
        if payload_patch:
            merged_payload.update(payload_patch)
        entity.payload = merged_payload
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def create_handoff(
        self,
        *,
        session_id: str,
        reason: str,
        trigger_flags: list[str] | None,
        operator: str,
        note: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> AIInterviewHandoff:
        entity = AIInterviewHandoff(
            session_id=session_id,
            reason=reason,
            trigger_flags=trigger_flags or [],
            operator=operator,
            note=note,
            payload=payload or {},
        )
        self._session.add(entity)
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def create_turn_event(
        self,
        *,
        session_id: str,
        event_id: str,
        speaker: str,
        transcript: str | None,
        audio_uri: str | None,
        confidence: float | None,
        latency_ms: int | None,
        policy_flags: list[str] | None,
        payload: dict[str, Any] | None,
        transcript_ttl_days: int = 180,
        audio_ttl_days: int = 30,
    ) -> tuple[AIInterviewTurn | None, bool]:
        session_entity = self.get(session_id)
        session_payload = dict(session_entity.payload or {})
        seen_event_ids = list(session_payload.get("seen_event_ids", []))
        if event_id in seen_event_ids:
            return None, True

        max_turn_stmt = select(func.max(AIInterviewTurn.turn_no)).where(AIInterviewTurn.session_id == session_id)
        current_max_turn_no = int(self._session.execute(max_turn_stmt).scalar_one() or 0)
        next_turn_no = current_max_turn_no + 1

        now = datetime.now(UTC).replace(tzinfo=None)
        turn_payload = dict(payload or {})
        turn_payload["event_id"] = event_id
        turn_entity = AIInterviewTurn(
            session_id=session_id,
            turn_no=next_turn_no,
            speaker=speaker,
            transcript=transcript,
            audio_uri=audio_uri,
            confidence=confidence,
            latency_ms=latency_ms,
            policy_flags=policy_flags or [],
            payload=turn_payload,
            transcript_expires_at=now + timedelta(days=max(1, transcript_ttl_days)),
            audio_expires_at=(now + timedelta(days=max(1, audio_ttl_days))) if audio_uri else None,
        )
        self._session.add(turn_entity)

        seen_event_ids.append(event_id)
        session_payload["seen_event_ids"] = seen_event_ids
        session_entity.payload = session_payload
        self._session.commit()
        self._session.refresh(turn_entity)
        return turn_entity, False

    def is_event_seen(self, *, session_id: str, event_id: str) -> bool:
        session_entity = self.get(session_id)
        seen_event_ids = list((session_entity.payload or {}).get("seen_event_ids", []))
        return event_id in seen_event_ids

    def get_latest_question_set_version(self, session_id: str | None = None, invitation_id: str | None = None) -> int:
        stmt = select(func.max(AIInterviewQuestionSet.version))
        if session_id:
            stmt = stmt.where(AIInterviewQuestionSet.session_id == session_id)
        if invitation_id:
            stmt = stmt.where(AIInterviewQuestionSet.invitation_id == invitation_id)
        return int(self._session.execute(stmt).scalar_one() or 0)

    def get_latest_question_set(self, session_id: str | None = None, invitation_id: str | None = None) -> AIInterviewQuestionSet | None:
        stmt = select(AIInterviewQuestionSet)
        if session_id:
            stmt = stmt.where(AIInterviewQuestionSet.session_id == session_id)
        if invitation_id:
            stmt = stmt.where(AIInterviewQuestionSet.invitation_id == invitation_id)
            
        stmt = stmt.order_by(desc(AIInterviewQuestionSet.version), desc(AIInterviewQuestionSet.created_at))
        return self._session.execute(stmt).scalars().first()

    def create_question_set(
        self,
        *,
        session_id: str | None = None,
        invitation_id: str | None = None,
        version: int,
        source: str,
        questions: list[dict[str, Any]],
    ) -> AIInterviewQuestionSet:
        entity = AIInterviewQuestionSet(
            session_id=session_id,
            invitation_id=invitation_id,
            version=version,
            source=source,
            questions_json=questions,
        )
        self._session.add(entity)
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def list_turns(self, session_id: str) -> list[AIInterviewTurn]:
        stmt = select(AIInterviewTurn).where(AIInterviewTurn.session_id == session_id).order_by(AIInterviewTurn.turn_no.asc())
        return list(self._session.execute(stmt).scalars().all())

    def list_recent_turns(self, session_id: str, *, limit: int = 4) -> list[AIInterviewTurn]:
        capped_limit = max(1, min(int(limit), 20))
        stmt = (
            select(AIInterviewTurn)
            .where(AIInterviewTurn.session_id == session_id)
            .order_by(AIInterviewTurn.turn_no.desc())
            .limit(capped_limit)
        )
        items = list(self._session.execute(stmt).scalars().all())
        items.reverse()
        return items

    def list_sessions(self, *, window_minutes: int) -> list[AIInterviewSession]:
        since = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=max(1, window_minutes))
        stmt = select(AIInterviewSession).where(AIInterviewSession.created_at >= since).order_by(AIInterviewSession.created_at.desc())
        return list(self._session.execute(stmt).scalars().all())

    def list_candidate_latencies(self, *, window_minutes: int) -> list[int]:
        since = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=max(1, window_minutes))
        stmt = (
            select(AIInterviewTurn.latency_ms)
            .where(AIInterviewTurn.created_at >= since)
            .where(AIInterviewTurn.speaker == "candidate")
            .where(AIInterviewTurn.latency_ms.is_not(None))
        )
        return [int(item) for item in self._session.execute(stmt).scalars().all()]

    def list_candidate_turns(self, *, window_minutes: int) -> list[AIInterviewTurn]:
        since = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=max(1, window_minutes))
        stmt = (
            select(AIInterviewTurn)
            .where(AIInterviewTurn.created_at >= since)
            .where(AIInterviewTurn.speaker == "candidate")
            .order_by(AIInterviewTurn.created_at.desc())
        )
        return list(self._session.execute(stmt).scalars().all())

    def get_latest_report(self, session_id: str) -> AIInterviewReport | None:
        stmt = (
            select(AIInterviewReport)
            .where(AIInterviewReport.session_id == session_id)
            .order_by(desc(AIInterviewReport.report_version), desc(AIInterviewReport.created_at))
        )
        return self._session.execute(stmt).scalars().first()

    def get_report_by_run_id(self, session_id: str, run_id: str) -> AIInterviewReport | None:
        stmt = (
            select(AIInterviewReport)
            .where(AIInterviewReport.session_id == session_id)
            .order_by(desc(AIInterviewReport.report_version), desc(AIInterviewReport.created_at))
        )
        reports = list(self._session.execute(stmt).scalars().all())
        for item in reports:
            if str((item.payload or {}).get("run_id", "")) == run_id:
                return item
        return None

    def create_report(
        self,
        *,
        session_id: str,
        report_version: int,
        summary: str,
        dimension_scores_json: dict[str, Any],
        risk_tags_json: list[str],
        recommendation: str,
        payload: dict[str, Any] | None = None,
    ) -> AIInterviewReport:
        entity = AIInterviewReport(
            session_id=session_id,
            report_version=report_version,
            summary=summary,
            dimension_scores_json=dimension_scores_json,
            risk_tags_json=risk_tags_json,
            recommendation=recommendation,
            payload=payload or {},
        )
        self._session.add(entity)
        self._session.commit()
        self._session.refresh(entity)
        return entity

class AIInterviewInvitationRepository:
    """Persistence layer for AI interview invitations."""

    def __init__(self, session: Session):
        self._session = session

    def create(
        self,
        *,
        candidate_id: str,
        job_id: str,
        token: str,
        expires_at: datetime,
        payload: dict[str, Any] | None = None,
        note: str | None = None,
    ) -> AIInterviewInvitation:
        entity = AIInterviewInvitation(
            candidate_id=candidate_id,
            job_id=job_id,
            token=token,
            status="pending",
            expires_at=expires_at,
            payload=payload or {},
            note=note,
        )
        self._session.add(entity)
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def get_by_id(self, invitation_id: str) -> AIInterviewInvitation:
        """通过 ID 获取邀请记录。"""
        entity = self._session.query(AIInterviewInvitation).get(invitation_id)
        if not entity:
            raise InvalidStateError(f"AI interview invitation with ID '{invitation_id}' not found")
        return entity

    def get_by_token(self, token: str) -> AIInterviewInvitation:
        stmt = select(AIInterviewInvitation).where(AIInterviewInvitation.token == token)
        entity = self._session.execute(stmt).scalar_one_or_none()
        if entity is None:
            raise ResourceNotFoundError(f"AI interview invitation with token '{token}' was not found")
        return entity

    def update_status(self, invitation_id: str, status: str) -> AIInterviewInvitation:
        stmt = select(AIInterviewInvitation).where(AIInterviewInvitation.id == invitation_id)
        entity = self._session.execute(stmt).scalar_one_or_none()
        if entity is None:
            raise ResourceNotFoundError(f"AI interview invitation '{invitation_id}' was not found")
        entity.status = status
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def mark_activated(self, invitation_id: str) -> AIInterviewInvitation:
        """Mark invitation as activated, increment used_count and update activated_at."""
        stmt = select(AIInterviewInvitation).where(AIInterviewInvitation.id == invitation_id)
        entity = self._session.execute(stmt).scalar_one_or_none()
        if entity is None:
            raise ResourceNotFoundError(f"AI interview invitation '{invitation_id}' was not found")
        
        entity.status = "started"
        entity.used_count += 1
        entity.activated_at = datetime.now(UTC).replace(tzinfo=None)
        
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def update_delivery(
        self,
        invitation_id: str,
        *,
        email_delivery_id: str | None = None,
        invitation_channel: str | None = None,
        payload_patch: dict[str, Any] | None = None,
    ) -> AIInterviewInvitation:
        stmt = select(AIInterviewInvitation).where(AIInterviewInvitation.id == invitation_id)
        entity = self._session.execute(stmt).scalar_one_or_none()
        if entity is None:
            raise ResourceNotFoundError(f"AI interview invitation '{invitation_id}' was not found")
        if email_delivery_id is not None:
            entity.email_delivery_id = email_delivery_id
        if invitation_channel is not None:
            entity.invitation_channel = invitation_channel
        if payload_patch:
            merged = dict(entity.payload or {})
            merged.update(payload_patch)
            entity.payload = merged
        self._session.commit()
        self._session.refresh(entity)
        return entity
