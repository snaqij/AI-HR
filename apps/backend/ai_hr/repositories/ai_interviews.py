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
from .workspace_scope import get_workspace_id


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
        safe_payload = payload or {}
        print(
            "[PERSIST][AIInterviewSession.create] preparing insert "
            f"candidate_id={candidate_id} job_id={job_id} channel={channel} language={language} "
            f"rtc_room_id={rtc_room_id} payload_keys={list(safe_payload.keys())}"
        )
        entity = AIInterviewSession(
            workspace_id=get_workspace_id(self._session),
            candidate_id=candidate_id,
            job_id=job_id,
            status="created",
            channel=channel,
            language=language,
            rtc_room_id=rtc_room_id,
            join_token=join_token,
            note=note,
            payload=safe_payload,
        )
        self._session.add(entity)
        self._session.commit()
        self._session.refresh(entity)
        print(
            "[PERSIST][AIInterviewSession.create] committed "
            f"id={entity.id} status={entity.status} created_at={entity.created_at}"
        )
        return entity

    def get(self, session_id: str) -> AIInterviewSession:
        stmt = select(AIInterviewSession).where(AIInterviewSession.id == session_id)
        workspace_id = get_workspace_id(self._session)
        if workspace_id:
            stmt = stmt.where(AIInterviewSession.workspace_id == workspace_id)
        entity = self._session.execute(stmt).scalar_one_or_none()
        if entity is None:
            raise ResourceNotFoundError(f"AI interview session '{session_id}' was not found")
        return entity

    def get_by_room_id(self, room_id: str) -> AIInterviewSession | None:
        stmt = select(AIInterviewSession).where(AIInterviewSession.rtc_room_id == room_id)
        workspace_id = get_workspace_id(self._session)
        if workspace_id:
            stmt = stmt.where(AIInterviewSession.workspace_id == workspace_id)
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
        before_status = entity.status
        before_payload = dict(entity.payload or {})
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
        print(
            "[PERSIST][AIInterviewSession.update_status] preparing update "
            f"session_id={session_id} status={before_status}->{status} "
            f"note_set={note is not None} "
            f"payload_patch_keys={list((payload_patch or {}).keys())} "
            f"payload_key_count={len(before_payload)}->{len(merged_payload)}"
        )
        self._session.commit()
        self._session.refresh(entity)
        print(
            "[PERSIST][AIInterviewSession.update_status] committed "
            f"id={entity.id} status={entity.status} started_at={entity.started_at} ended_at={entity.ended_at}"
        )
        return entity

    def update_payload(self, session_id: str, *, payload_patch: dict[str, Any]) -> AIInterviewSession:
        entity = self.get(session_id)
        merged_payload = dict(entity.payload or {})
        merged_payload.update(payload_patch or {})
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
        question_attempt_id: str | None = None,
        question_id: str | None = None,
        question_seq: int | None = None,
        ingest_trace_id: str | None = None,
        policy_flags: list[str] | None = None,
        payload: dict[str, Any] | None = None,
        transcript_ttl_days: int = 180,
        audio_ttl_days: int = 30,
    ) -> tuple[AIInterviewTurn | None, bool]:
        session_entity = self.get(session_id)
        session_payload = dict(session_entity.payload or {})
        seen_event_ids = list(session_payload.get("seen_event_ids", []))
        if event_id in seen_event_ids:
            print(
                "[PERSIST][AIInterviewTurn.create_turn_event] deduplicated "
                f"session_id={session_id} event_id={event_id} speaker={speaker}"
            )
            return None, True

        max_turn_stmt = select(func.max(AIInterviewTurn.turn_no)).where(AIInterviewTurn.session_id == session_id)
        current_max_turn_no = int(self._session.execute(max_turn_stmt).scalar_one() or 0)
        next_turn_no = current_max_turn_no + 1

        now = datetime.now(UTC).replace(tzinfo=None)
        turn_payload = dict(payload or {})
        turn_payload["event_id"] = event_id
        transcript_preview = (transcript or "").strip().replace("\n", " ")
        if len(transcript_preview) > 120:
            transcript_preview = transcript_preview[:120] + "..."
        print(
            "[PERSIST][AIInterviewTurn.create_turn_event] preparing insert "
            f"session_id={session_id} turn_no={next_turn_no} event_id={event_id} speaker={speaker} "
            f"question_id={question_id} question_seq={question_seq} question_attempt_id={question_attempt_id} "
            f"confidence={confidence} latency_ms={latency_ms} "
            f"policy_flags={policy_flags or []} transcript={transcript_preview!r} "
            f"payload_keys={list(turn_payload.keys())}"
        )
        turn_entity = AIInterviewTurn(
            session_id=session_id,
            turn_no=next_turn_no,
            question_attempt_id=question_attempt_id,
            question_id=question_id,
            question_seq=question_seq,
            speaker=speaker,
            transcript=transcript,
            audio_uri=audio_uri,
            confidence=confidence,
            latency_ms=latency_ms,
            ingest_trace_id=ingest_trace_id,
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
        print(
            "[PERSIST][AIInterviewTurn.create_turn_event] committed "
            f"id={turn_entity.id} session_id={turn_entity.session_id} turn_no={turn_entity.turn_no} "
            f"speaker={turn_entity.speaker} created_at={turn_entity.created_at}"
        )
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
        print(
            "[PERSIST][AIInterviewQuestionSet.create] preparing insert "
            f"session_id={session_id} invitation_id={invitation_id} version={version} source={source} "
            f"question_count={len(questions or [])}"
        )
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
        print(
            "[PERSIST][AIInterviewQuestionSet.create] committed "
            f"id={entity.id} version={entity.version} created_at={entity.created_at}"
        )
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
        workspace_id = get_workspace_id(self._session)
        if workspace_id:
            stmt = stmt.where(AIInterviewSession.workspace_id == workspace_id)
        return list(self._session.execute(stmt).scalars().all())

    def list_candidate_latencies(self, *, window_minutes: int) -> list[int]:
        since = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=max(1, window_minutes))
        stmt = (
            select(AIInterviewTurn.latency_ms)
            .where(AIInterviewTurn.created_at >= since)
            .where(AIInterviewTurn.speaker == "candidate")
            .where(AIInterviewTurn.latency_ms.is_not(None))
        )
        workspace_id = get_workspace_id(self._session)
        if workspace_id:
            stmt = stmt.join(AIInterviewSession, AIInterviewSession.id == AIInterviewTurn.session_id).where(
                AIInterviewSession.workspace_id == workspace_id
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
        workspace_id = get_workspace_id(self._session)
        if workspace_id:
            stmt = stmt.join(AIInterviewSession, AIInterviewSession.id == AIInterviewTurn.session_id).where(
                AIInterviewSession.workspace_id == workspace_id
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
        print(
            "[PERSIST][AIInterviewReport.create] preparing insert "
            f"session_id={session_id} report_version={report_version} recommendation={recommendation} "
            f"summary_len={len(summary or '')} "
            f"dimension_keys={list((dimension_scores_json or {}).keys())} "
            f"risk_tags={risk_tags_json or []} "
            f"payload_keys={list((payload or {}).keys())}"
        )
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
        print(
            "[PERSIST][AIInterviewReport.create] committed "
            f"id={entity.id} session_id={entity.session_id} report_version={entity.report_version} created_at={entity.created_at}"
        )
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
        safe_payload = payload or {}
        print(
            "[PERSIST][AIInterviewInvitation.create] preparing insert "
            f"candidate_id={candidate_id} job_id={job_id} expires_at={expires_at} "
            f"token={token} payload_keys={list(safe_payload.keys())}"
        )
        entity = AIInterviewInvitation(
            candidate_id=candidate_id,
            job_id=job_id,
            token=token,
            status="pending",
            expires_at=expires_at,
            payload=safe_payload,
            note=note,
        )
        self._session.add(entity)
        self._session.commit()
        self._session.refresh(entity)
        print(
            "[PERSIST][AIInterviewInvitation.create] committed "
            f"id={entity.id} status={entity.status} created_at={entity.created_at}"
        )
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
        before_status = entity.status
        print(
            "[PERSIST][AIInterviewInvitation.update_status] preparing update "
            f"invitation_id={invitation_id} status={before_status}->{status}"
        )
        entity.status = status
        self._session.commit()
        self._session.refresh(entity)
        print(
            "[PERSIST][AIInterviewInvitation.update_status] committed "
            f"id={entity.id} status={entity.status} updated_at={entity.updated_at}"
        )
        return entity

    def update_payload(self, invitation_id: str, *, payload_patch: dict[str, Any]) -> AIInterviewInvitation:
        stmt = select(AIInterviewInvitation).where(AIInterviewInvitation.id == invitation_id)
        entity = self._session.execute(stmt).scalar_one_or_none()
        if entity is None:
            raise ResourceNotFoundError(f"AI interview invitation '{invitation_id}' was not found")
        merged = dict(entity.payload or {})
        merged.update(payload_patch or {})
        entity.payload = merged
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def mark_activated(self, invitation_id: str) -> AIInterviewInvitation:
        """Mark invitation as activated, increment used_count and update activated_at."""
        stmt = select(AIInterviewInvitation).where(AIInterviewInvitation.id == invitation_id)
        entity = self._session.execute(stmt).scalar_one_or_none()
        if entity is None:
            raise ResourceNotFoundError(f"AI interview invitation '{invitation_id}' was not found")
        print(
            "[PERSIST][AIInterviewInvitation.mark_activated] preparing update "
            f"invitation_id={invitation_id} status={entity.status}->started "
            f"used_count={entity.used_count}->{entity.used_count + 1}"
        )
        entity.status = "started"
        entity.used_count += 1
        entity.activated_at = datetime.now(UTC).replace(tzinfo=None)
        
        self._session.commit()
        self._session.refresh(entity)
        print(
            "[PERSIST][AIInterviewInvitation.mark_activated] committed "
            f"id={entity.id} status={entity.status} used_count={entity.used_count} activated_at={entity.activated_at}"
        )
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
