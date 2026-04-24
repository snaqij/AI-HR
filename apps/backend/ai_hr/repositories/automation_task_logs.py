"""Repository for automation task audit logs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from ..core.exceptions import ResourceNotFoundError
from ..db.models import AutomationTaskLog


class AutomationTaskLogRepository:
    """Creates and updates execution logs for background automation tasks."""

    def __init__(self, session: Session):
        self._session = session

    def get(self, log_id: str) -> AutomationTaskLog:
        entity = self._session.get(AutomationTaskLog, log_id)
        if entity is None:
            raise ResourceNotFoundError(f"Automation task log '{log_id}' was not found")
        return entity

    def create(
        self,
        *,
        task_type: str,
        task_name: str,
        status: str = "pending",
        trigger_mode: str = "scheduler",
        entity_type: str | None = None,
        entity_id: str | None = None,
        candidate_id: str | None = None,
        job_id: str | None = None,
        request_payload: dict[str, Any] | None = None,
    ) -> AutomationTaskLog:
        entity = AutomationTaskLog(
            task_type=task_type,
            task_name=task_name,
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

    def mark_running(self, log_id: str) -> AutomationTaskLog:
        entity = self.get(log_id)
        entity.status = "running"
        entity.started_at = datetime.now(UTC).replace(tzinfo=None)
        entity.finished_at = None
        entity.duration_ms = None
        self._session.flush()
        return entity

    def mark_succeeded(self, log_id: str, *, result_payload: dict[str, Any] | None = None) -> AutomationTaskLog:
        entity = self.get(log_id)
        finished_at = datetime.now(UTC).replace(tzinfo=None)
        entity.status = "success"
        entity.finished_at = finished_at
        entity.result_payload = result_payload
        entity.error_code = None
        entity.error_message = None
        entity.duration_ms = self._calc_duration_ms(entity.started_at, finished_at)
        self._session.flush()
        return entity

    def mark_failed(
        self,
        log_id: str,
        *,
        error_message: str,
        error_code: str | None = None,
        result_payload: dict[str, Any] | None = None,
    ) -> AutomationTaskLog:
        entity = self.get(log_id)
        finished_at = datetime.now(UTC).replace(tzinfo=None)
        entity.status = "failed"
        entity.finished_at = finished_at
        entity.error_code = error_code
        entity.error_message = error_message
        entity.result_payload = result_payload
        entity.retry_count += 1
        entity.duration_ms = self._calc_duration_ms(entity.started_at, finished_at)
        self._session.flush()
        return entity

    def _calc_duration_ms(self, started_at: datetime | None, finished_at: datetime) -> int | None:
        if started_at is None:
            return None
        delta = finished_at - started_at
        return int(delta.total_seconds() * 1000)
