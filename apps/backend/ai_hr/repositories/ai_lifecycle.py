"""AI 面试数据生命周期清理仓储。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..db.models import AIInterviewTurn, Event


class AIInterviewLifecycleRepository:
    """封装转写/音频/事件生命周期清理。"""

    def __init__(self, session: Session):
        self._session = session

    def list_expired_transcript_turn_ids(self, *, cutoff: datetime, limit: int) -> list[str]:
        stmt = (
            select(AIInterviewTurn.id)
            .where(AIInterviewTurn.transcript_expires_at.is_not(None))
            .where(AIInterviewTurn.transcript_expires_at < cutoff)
            .where(AIInterviewTurn.transcript.is_not(None))
            .order_by(AIInterviewTurn.transcript_expires_at.asc())
            .limit(max(1, limit))
        )
        return [str(item) for item in self._session.execute(stmt).scalars().all()]

    def clear_transcripts(self, *, turn_ids: list[str], cleaned_at: datetime, dry_run: bool) -> int:
        if not turn_ids:
            return 0
        if dry_run:
            return len(turn_ids)
        turns = (
            self._session.execute(select(AIInterviewTurn).where(AIInterviewTurn.id.in_(turn_ids)))
            .scalars()
            .all()
        )
        for turn in turns:
            payload = dict(turn.payload or {})
            payload["transcript_cleaned_at"] = cleaned_at.isoformat()
            turn.payload = payload
            turn.transcript = None
        self._session.commit()
        return len(turns)

    def list_expired_audio_turn_ids(self, *, cutoff: datetime, limit: int) -> list[str]:
        stmt = (
            select(AIInterviewTurn.id)
            .where(AIInterviewTurn.audio_expires_at.is_not(None))
            .where(AIInterviewTurn.audio_expires_at < cutoff)
            .where(AIInterviewTurn.audio_uri.is_not(None))
            .order_by(AIInterviewTurn.audio_expires_at.asc())
            .limit(max(1, limit))
        )
        return [str(item) for item in self._session.execute(stmt).scalars().all()]

    def clear_audio_uris(self, *, turn_ids: list[str], cleaned_at: datetime, dry_run: bool) -> int:
        if not turn_ids:
            return 0
        if dry_run:
            return len(turn_ids)
        turns = (
            self._session.execute(select(AIInterviewTurn).where(AIInterviewTurn.id.in_(turn_ids)))
            .scalars()
            .all()
        )
        for turn in turns:
            payload = dict(turn.payload or {})
            payload["audio_cleaned_at"] = cleaned_at.isoformat()
            turn.payload = payload
            turn.audio_uri = None
        self._session.commit()
        return len(turns)

    def list_expired_ai_event_ids(self, *, cutoff: datetime, limit: int) -> list[str]:
        stmt = (
            select(Event.id)
            .where(Event.occurred_at < cutoff)
            .where(Event.event_type.like("ai_interview.%"))
            .order_by(Event.occurred_at.asc())
            .limit(max(1, limit))
        )
        return [str(item) for item in self._session.execute(stmt).scalars().all()]

    def delete_events(self, *, event_ids: list[str], dry_run: bool) -> int:
        if not event_ids:
            return 0
        if dry_run:
            return len(event_ids)
        stmt = delete(Event).where(Event.id.in_(event_ids))
        result = self._session.execute(stmt)
        self._session.commit()
        return int(result.rowcount or 0)

    def create_cleanup_audit_event(self, *, payload: dict[str, Any]) -> str:
        event = Event(
            event_type="ai_interview.lifecycle.cleanup",
            entity_type="ai_interview_session",
            entity_id="batch",
            status="success",
            operator="system",
            payload=payload,
        )
        self._session.add(event)
        self._session.commit()
        self._session.refresh(event)
        return str(event.id)
