"""岗位同步任务与执行流水仓储。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.exceptions import ResourceNotFoundError
from ..db.models import JobSyncRun, JobSyncTask


class JobSyncTaskRepository:
    """管理同步任务配置。"""

    def __init__(self, session: Session):
        self._session = session

    def upsert(
        self,
        *,
        job_id: str,
        channel: str,
        enabled: bool,
        interval_minutes: int,
        max_pages: int,
        reset_cursor_on_next_run: bool,
        auto_request_resume: bool,
        auto_sync_resume_attachment: bool,
        next_run_at: datetime | None,
    ) -> JobSyncTask:
        stmt = select(JobSyncTask).where(JobSyncTask.job_id == job_id, JobSyncTask.channel == channel)
        entity = self._session.execute(stmt).scalar_one_or_none()
        if entity is None:
            entity = JobSyncTask(
                job_id=job_id,
                channel=channel,
                enabled=enabled,
                interval_minutes=interval_minutes,
                max_pages=max_pages,
                reset_cursor_on_next_run=reset_cursor_on_next_run,
                auto_request_resume=auto_request_resume,
                auto_sync_resume_attachment=auto_sync_resume_attachment,
                next_run_at=next_run_at,
            )
            self._session.add(entity)
        else:
            entity.enabled = enabled
            entity.interval_minutes = interval_minutes
            entity.max_pages = max_pages
            entity.reset_cursor_on_next_run = reset_cursor_on_next_run
            entity.auto_request_resume = auto_request_resume
            entity.auto_sync_resume_attachment = auto_sync_resume_attachment
            entity.next_run_at = next_run_at
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def get(self, task_id: str) -> JobSyncTask:
        entity = self._session.get(JobSyncTask, task_id)
        if entity is None:
            raise ResourceNotFoundError(f"Job sync task '{task_id}' was not found")
        return entity

    def list_by_job(self, job_id: str) -> list[JobSyncTask]:
        stmt = select(JobSyncTask).where(JobSyncTask.job_id == job_id).order_by(JobSyncTask.created_at.desc())
        return list(self._session.execute(stmt).scalars().all())

    def list_due(self, *, now: datetime, limit: int) -> list[JobSyncTask]:
        stmt = (
            select(JobSyncTask)
            .where(
                JobSyncTask.enabled.is_(True),
                JobSyncTask.next_run_at.is_not(None),
                JobSyncTask.next_run_at <= now,
            )
            .order_by(JobSyncTask.next_run_at.asc())
            .limit(max(1, limit))
        )
        return list(self._session.execute(stmt).scalars().all())

    def mark_result(
        self,
        task_id: str,
        *,
        status: str,
        error_message: str | None = None,
        next_run_at: datetime | None = None,
        clear_reset_cursor: bool = False,
    ) -> JobSyncTask:
        entity = self.get(task_id)
        entity.last_run_at = datetime.now(UTC).replace(tzinfo=None)
        entity.last_status = status
        entity.last_error = error_message
        entity.next_run_at = next_run_at
        if clear_reset_cursor:
            entity.reset_cursor_on_next_run = False
        self._session.commit()
        self._session.refresh(entity)
        return entity


class JobSyncRunRepository:
    """管理同步执行流水。"""

    def __init__(self, session: Session):
        self._session = session

    def create(
        self,
        *,
        task_id: str | None,
        job_id: str,
        trigger_type: str,
        channel: str | None,
        max_pages: int,
        reset_cursor: bool,
    ) -> JobSyncRun:
        entity = JobSyncRun(
            task_id=task_id,
            job_id=job_id,
            trigger_type=trigger_type,
            status="running",
            channel=channel,
            max_pages=max_pages,
            reset_cursor=reset_cursor,
            started_at=datetime.now(UTC).replace(tzinfo=None),
        )
        self._session.add(entity)
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def complete(
        self,
        run_id: str,
        *,
        status: str,
        total_pulled: int,
        total_created: int,
        total_updated: int,
        summary_payload: dict,
        error_message: str | None = None,
    ) -> JobSyncRun:
        entity = self._session.get(JobSyncRun, run_id)
        if entity is None:
            raise ResourceNotFoundError(f"Job sync run '{run_id}' was not found")
        entity.status = status
        entity.total_pulled = total_pulled
        entity.total_created = total_created
        entity.total_updated = total_updated
        entity.summary_payload = summary_payload or {}
        entity.error_message = error_message
        entity.finished_at = datetime.now(UTC).replace(tzinfo=None)
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def list_by_job(self, job_id: str, limit: int = 20) -> list[JobSyncRun]:
        stmt = (
            select(JobSyncRun)
            .where(JobSyncRun.job_id == job_id)
            .order_by(JobSyncRun.started_at.desc())
            .limit(max(1, min(limit, 200)))
        )
        return list(self._session.execute(stmt).scalars().all())


def compute_next_run_at(interval_minutes: int, *, now: datetime | None = None) -> datetime:
    base = now or datetime.now(UTC).replace(tzinfo=None)
    return base + timedelta(minutes=max(1, interval_minutes))
