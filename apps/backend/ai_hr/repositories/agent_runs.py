"""Repository for agent run lifecycle records."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.exceptions import ResourceNotFoundError
from ..db.models import AgentRun


class AgentRunRepository:
    """Creates and updates schedulable agent run records."""

    def __init__(self, session: Session):
        self._session = session

    def get(self, run_id: str) -> AgentRun:
        entity = self._session.get(AgentRun, run_id)
        if entity is None:
            raise ResourceNotFoundError(f"Agent run '{run_id}' was not found")
        return entity

    def create(
        self,
        *,
        agent_code: str,
        task_type: str,
        status: str = "pending",
        agent_type: str = "worker",
        trigger_mode: str = "scheduler",
        run_key: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        candidate_id: str | None = None,
        job_id: str | None = None,
        request_payload: dict[str, Any] | None = None,
    ) -> AgentRun:
        entity = AgentRun(
            run_key=run_key,
            agent_code=agent_code,
            agent_type=agent_type,
            task_type=task_type,
            status=status,
            trigger_mode=trigger_mode,
            entity_type=entity_type,
            entity_id=entity_id,
            candidate_id=candidate_id,
            job_id=job_id,
            request_payload=request_payload,
            started_at=datetime.now(UTC).replace(tzinfo=None) if status == "running" else None,
        )
        self._session.add(entity)
        self._session.flush()
        return entity

    def mark_running(self, run_id: str) -> AgentRun:
        entity = self.get(run_id)
        entity.status = "running"
        entity.started_at = datetime.now(UTC).replace(tzinfo=None)
        entity.finished_at = None
        entity.duration_ms = None
        entity.error_code = None
        entity.error_message = None
        self._session.flush()
        return entity

    def mark_succeeded(self, run_id: str, *, result_payload: dict[str, Any] | None = None) -> AgentRun:
        entity = self.get(run_id)
        finished_at = datetime.now(UTC).replace(tzinfo=None)
        entity.status = "completed"
        entity.finished_at = finished_at
        entity.result_payload = result_payload
        entity.error_code = None
        entity.error_message = None
        entity.duration_ms = self._calc_duration_ms(entity.started_at, finished_at)
        self._session.flush()
        return entity

    def mark_failed(
        self,
        run_id: str,
        *,
        error_message: str,
        error_code: str | None = None,
        result_payload: dict[str, Any] | None = None,
    ) -> AgentRun:
        entity = self.get(run_id)
        finished_at = datetime.now(UTC).replace(tzinfo=None)
        entity.status = "failed"
        entity.finished_at = finished_at
        entity.error_code = error_code
        entity.error_message = error_message
        entity.result_payload = result_payload
        entity.duration_ms = self._calc_duration_ms(entity.started_at, finished_at)
        self._session.flush()
        return entity

    def list(
        self,
        *,
        agent_code: str | None = None,
        task_type: str | None = None,
        status: str | None = None,
        candidate_id: str | None = None,
        job_id: str | None = None,
        limit: int = 100,
    ) -> list[AgentRun]:
        stmt = select(AgentRun)
        if agent_code:
            stmt = stmt.where(AgentRun.agent_code == agent_code)
        if task_type:
            stmt = stmt.where(AgentRun.task_type == task_type)
        if status:
            stmt = stmt.where(AgentRun.status == status)
        if candidate_id:
            stmt = stmt.where(AgentRun.candidate_id == candidate_id)
        if job_id:
            stmt = stmt.where(AgentRun.job_id == job_id)
        stmt = stmt.order_by(AgentRun.created_at.desc()).limit(max(1, min(limit, 300)))
        return list(self._session.execute(stmt).scalars().all())

    def _calc_duration_ms(self, started_at: datetime | None, finished_at: datetime) -> int | None:
        if started_at is None:
            return None
        return int((finished_at - started_at).total_seconds() * 1000)
