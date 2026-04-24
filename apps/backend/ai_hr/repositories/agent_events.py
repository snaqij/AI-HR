"""Repository for agent run event stream records."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import AgentEvent


class AgentEventRepository:
    """Persists and queries stage events emitted by agent runs."""

    def __init__(self, session: Session):
        self._session = session

    def create(
        self,
        *,
        run_id: str,
        agent_code: str,
        event_name: str,
        event_type: str = "run",
        status: str = "info",
        message: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        candidate_id: str | None = None,
        job_id: str | None = None,
        payload: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> AgentEvent:
        sequence_no = self._next_sequence_no(run_id)
        entity = AgentEvent(
            run_id=run_id,
            sequence_no=sequence_no,
            agent_code=agent_code,
            event_type=event_type,
            event_name=event_name,
            status=status,
            message=message,
            entity_type=entity_type,
            entity_id=entity_id,
            candidate_id=candidate_id,
            job_id=job_id,
            payload=payload or {},
            occurred_at=occurred_at or datetime.now(UTC).replace(tzinfo=None),
        )
        self._session.add(entity)
        self._session.flush()
        return entity

    def list(
        self,
        *,
        run_id: str | None = None,
        agent_code: str | None = None,
        status: str | None = None,
        candidate_id: str | None = None,
        job_id: str | None = None,
        limit: int = 200,
    ) -> list[AgentEvent]:
        stmt = select(AgentEvent)
        if run_id:
            stmt = stmt.where(AgentEvent.run_id == run_id)
        if agent_code:
            stmt = stmt.where(AgentEvent.agent_code == agent_code)
        if status:
            stmt = stmt.where(AgentEvent.status == status)
        if candidate_id:
            stmt = stmt.where(AgentEvent.candidate_id == candidate_id)
        if job_id:
            stmt = stmt.where(AgentEvent.job_id == job_id)
        stmt = stmt.order_by(AgentEvent.occurred_at.desc(), AgentEvent.sequence_no.desc()).limit(max(1, min(limit, 500)))
        return list(self._session.execute(stmt).scalars().all())

    def _next_sequence_no(self, run_id: str) -> int:
        stmt = select(func.max(AgentEvent.sequence_no)).where(AgentEvent.run_id == run_id)
        latest = self._session.execute(stmt).scalar_one_or_none()
        return int(latest or 0) + 1
