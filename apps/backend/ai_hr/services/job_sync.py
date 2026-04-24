"""岗位候选人同步调度与执行服务。"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.exceptions import CredentialsExpiredError
from ..db.models import TeamWorkspace
from ..db.session import SessionLocal
from ..repositories.events import EventRepository
from ..repositories.job_sync import JobSyncRunRepository, JobSyncTaskRepository, compute_next_run_at
from ..repositories.jobs import JobRepository
from ..schemas.ai_resume import ResumeAccessBatchSyncRequest
from ..schemas.job_sync import JobSyncTaskUpsertRequest
from ..schemas.jobs import JobCandidateSyncRequest
from .ai_resume import AIResumeService, get_ai_resume_service
from .jobs import JobService, get_job_service
from .recruitment_automation import get_recruitment_automation_service
from .credentials import get_credential_service

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SchedulerExecutionContext:
    workspace_id: str | None
    owner_user_id: str | None

    @property
    def log_key(self) -> str:
        return self.workspace_id or "default"


class JobSyncService:
    """对手动同步、定时任务与审计流水做统一编排。"""

    def __init__(
        self,
        session: Session,
        job_service: JobService,
        ai_resume_service: AIResumeService,
        job_repository: JobRepository,
        task_repository: JobSyncTaskRepository,
        run_repository: JobSyncRunRepository,
        event_repository: EventRepository,
    ):
        self._session = session
        self._job_service = job_service
        self._ai_resume_service = ai_resume_service
        self._job_repository = job_repository
        self._task_repository = task_repository
        self._run_repository = run_repository
        self._event_repository = event_repository
        self._settings = get_settings()

    def upsert_task(self, job_id: str, payload: JobSyncTaskUpsertRequest):
        self._job_repository.get(job_id)
        next_run_at = datetime.now(UTC).replace(tzinfo=None) if payload.run_immediately else compute_next_run_at(payload.interval_minutes)
        return self._task_repository.upsert(
            job_id=job_id,
            channel=payload.channel,
            enabled=payload.enabled,
            interval_minutes=payload.interval_minutes,
            max_pages=payload.max_pages,
            reset_cursor_on_next_run=payload.reset_cursor_on_next_run,
            auto_request_resume=payload.auto_request_resume,
            auto_sync_resume_attachment=payload.auto_sync_resume_attachment,
            next_run_at=next_run_at if payload.enabled else None,
        )

    def list_tasks(self, job_id: str):
        self._job_repository.get(job_id)
        return self._task_repository.list_by_job(job_id)

    def list_runs(self, job_id: str, limit: int = 20):
        self._job_repository.get(job_id)
        return self._run_repository.list_by_job(job_id, limit=limit)

    def run_manual_sync(self, job_id: str, payload: JobCandidateSyncRequest):
        channels = payload.channels or ["boss"]
        primary_channel = channels[0] if channels else None
        run = self._run_repository.create(
            task_id=None,
            job_id=job_id,
            trigger_type="manual",
            channel=primary_channel,
            max_pages=payload.max_pages,
            reset_cursor=payload.reset_cursor,
        )
        run_id = run.id
        try:
            result = self._job_service.sync_candidates(job_id, payload)
            result["metadata_enriched_count"] = self._maybe_enrich_synced_candidates(result)
            result["resume_access"] = self._maybe_sync_resume_access(job_id, payload, result)
            run = self._run_repository.complete(
                run_id,
                status="success",
                total_pulled=result["total_pulled"],
                total_created=result["total_created"],
                total_updated=result["total_updated"],
                summary_payload=result,
            )
            self._event_repository.create(
                event_type="job.sync.manual.completed",
                entity_type="job_sync_run",
                entity_id=run.id,
                job_id=job_id,
                channel=primary_channel,
                payload=result,
            )
            return result
        except Exception as exc:
            self._session.rollback()
            self._run_repository.complete(
                run_id,
                status="failed",
                total_pulled=0,
                total_created=0,
                total_updated=0,
                summary_payload={},
                error_message=str(exc),
            )
            self._event_repository.create(
                event_type="job.sync.manual.failed",
                entity_type="job_sync_run",
                entity_id=run_id,
                status="failed",
                job_id=job_id,
                channel=primary_channel,
                payload={"error": str(exc)},
            )
            raise

    def execute_task(self, task_id: str):
        task = self._task_repository.get(task_id)
        logger.info(
            "job_sync.task.start task_id=%s job_id=%s channel=%s max_pages=%s auto_request_resume=%s auto_sync_resume_attachment=%s",
            task.id,
            task.job_id,
            task.channel,
            task.max_pages,
            task.auto_request_resume,
            task.auto_sync_resume_attachment,
        )
        payload = JobCandidateSyncRequest(
            channels=[task.channel],
            max_pages=task.max_pages,
            reset_cursor=task.reset_cursor_on_next_run,
            auto_request_resume=task.auto_request_resume,
            auto_sync_resume_attachment=task.auto_sync_resume_attachment,
        )
        run = self._run_repository.create(
            task_id=task.id,
            job_id=task.job_id,
            trigger_type="scheduled",
            channel=task.channel,
            max_pages=task.max_pages,
            reset_cursor=task.reset_cursor_on_next_run,
        )
        run_id = run.id
        try:
            result = self._job_service.sync_candidates(task.job_id, payload)
            result["metadata_enriched_count"] = self._maybe_enrich_synced_candidates(result)
            result["resume_access"] = self._maybe_sync_resume_access(task.job_id, payload, result)
            run = self._run_repository.complete(
                run_id,
                status="success",
                total_pulled=result["total_pulled"],
                total_created=result["total_created"],
                total_updated=result["total_updated"],
                summary_payload=result,
            )
            task = self._task_repository.mark_result(
                task.id,
                status="success",
                next_run_at=compute_next_run_at(task.interval_minutes),
                clear_reset_cursor=True,
            )
            self._event_repository.create(
                event_type="job.sync.scheduled.completed",
                entity_type="job_sync_run",
                entity_id=run.id,
                job_id=task.job_id,
                channel=task.channel,
                payload=result,
            )
            logger.info(
                "job_sync.task.success task_id=%s job_id=%s channel=%s total_pulled=%s total_created=%s total_updated=%s",
                task.id,
                task.job_id,
                task.channel,
                result["total_pulled"],
                result["total_created"],
                result["total_updated"],
            )
            return {"task": task, "run": run, "summary": result}
        except Exception as exc:
            self._session.rollback()
            task = self._task_repository.mark_result(
                task.id,
                status="failed",
                error_message=str(exc),
                next_run_at=compute_next_run_at(task.interval_minutes),
                clear_reset_cursor=False,
            )
            run = self._run_repository.complete(
                run_id,
                status="failed",
                total_pulled=0,
                total_created=0,
                total_updated=0,
                summary_payload={},
                error_message=str(exc),
            )
            self._event_repository.create(
                event_type="job.sync.scheduled.failed",
                entity_type="job_sync_run",
                entity_id=run_id,
                status="failed",
                job_id=task.job_id,
                channel=task.channel,
                payload={"error": str(exc)},
            )
            logger.exception(
                "job_sync.task.failed task_id=%s job_id=%s channel=%s",
                task.id,
                task.job_id,
                task.channel,
            )
            raise

    def execute_due_tasks(self, limit: int | None = None) -> list[dict]:
        now = datetime.now(UTC).replace(tzinfo=None)
        due_tasks = self._task_repository.list_due(
            now=now,
            limit=limit or self._settings.job_sync_scheduler_batch_size,
        )
        logger.info(
            "job_sync.due_tasks.scan due_count=%s limit=%s",
            len(due_tasks),
            limit or self._settings.job_sync_scheduler_batch_size,
        )
        results: list[dict] = []
        for task in due_tasks:
            try:
                results.append(self.execute_task(task.id))
            except Exception:
                continue
        return results

    def execute_global_job_sync(self):
        """同步渠道侧新发布的岗位到本地库。"""
        channels = ["boss"]  # Currently only supports boss; extensible later
        results = []
        for channel in channels:
            try:
                logger.info("job_sync.global_sync.start channel=%s", channel)
                res = self._job_service.import_remote_jobs(
                    channel=channel, 
                    page=1, 
                    page_size=self._settings.job_global_sync_max_pages * 20
                )
                results.append(res)
                logger.info(
                    "job_sync.global_sync.success channel=%s created_count=%s updated_count=%s total_jobs=%s",
                    channel,
                    res.get("created_count", 0),
                    res.get("updated_count", 0),
                    len(res.get("jobs", [])),
                )
            except Exception:
                logger.exception("job_sync.global_sync.failed channel=%s", channel)
        return results

    def _maybe_sync_resume_access(
        self,
        job_id: str,
        payload: JobCandidateSyncRequest,
        sync_result: dict,
    ):
        job = self._job_repository.get(job_id)
        should_request_resume = bool(payload.auto_request_resume or getattr(job, "auto_request_resume", False))
        should_sync_attachment = bool(payload.auto_sync_resume_attachment)

        if not (should_request_resume or should_sync_attachment):
            return None
        candidate_ids = list(dict.fromkeys(sync_result.get("synced_candidate_ids", [])))
        if not candidate_ids:
            return None
        result = self._ai_resume_service.sync_job_resume_access(
            job_id,
            ResumeAccessBatchSyncRequest(
                candidate_ids=candidate_ids,
                sync_attachment_when_ready=should_sync_attachment,
            ),
        )
        return result.model_dump(mode="json")

    def _maybe_enrich_synced_candidates(self, sync_result: dict) -> int:
        candidate_ids = list(dict.fromkeys(sync_result.get("synced_candidate_ids", [])))
        if not candidate_ids:
            return 0
        return self._job_service.enrich_candidate_metadata(
            limit=len(candidate_ids),
            candidate_ids=candidate_ids,
        )


def get_job_sync_service(session: Session) -> JobSyncService:
    return JobSyncService(
        session=session,
        job_service=get_job_service(session),
        ai_resume_service=get_ai_resume_service(session),
        job_repository=JobRepository(session),
        task_repository=JobSyncTaskRepository(session),
        run_repository=JobSyncRunRepository(session),
        event_repository=EventRepository(session),
    )


@dataclass
class JobSyncScheduler:
    """简单的后台轮询执行器。"""

    stop_event: threading.Event
    thread: threading.Thread | None = None
    _last_global_sync_at_by_workspace: dict[str, float] | None = None
    _boss_paused_by_workspace: dict[str, bool] | None = None

    def start(self) -> None:
        settings = get_settings()
        if not settings.job_sync_scheduler_enabled or (self.thread and self.thread.is_alive()):
            return
        self.thread = threading.Thread(target=self._run_loop, name="job-sync-scheduler", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3)

    def _list_execution_contexts(self) -> list[SchedulerExecutionContext]:
        settings = get_settings()
        if not settings.auth_enabled:
            return [SchedulerExecutionContext(workspace_id="default", owner_user_id="system")]

        with SessionLocal() as session:
            rows = session.execute(
                select(TeamWorkspace.id, TeamWorkspace.owner_user_id)
                .where(TeamWorkspace.status == "active")
                .order_by(TeamWorkspace.created_at.asc())
            ).all()
        return [
            SchedulerExecutionContext(workspace_id=workspace_id, owner_user_id=owner_user_id)
            for workspace_id, owner_user_id in rows
            if workspace_id and owner_user_id
        ]

    def _run_loop(self) -> None:
        settings = get_settings()
        if self._last_global_sync_at_by_workspace is None:
            self._last_global_sync_at_by_workspace = {}
        if self._boss_paused_by_workspace is None:
            self._boss_paused_by_workspace = {}

        while not self.stop_event.is_set():
            contexts = self._list_execution_contexts()
            if not contexts and settings.auth_enabled:
                logger.debug("JobSyncScheduler: no active workspace contexts available")

            for context in contexts:
                session = SessionLocal()
                session.info["workspace_id"] = context.workspace_id
                session.info["user_id"] = context.owner_user_id
                workspace_key = context.log_key

                try:
                    service = get_job_sync_service(session)
                    credential_service = get_credential_service(session)
                    boss_paused = credential_service.is_channel_paused("boss")
                    previous_paused = self._boss_paused_by_workspace.get(workspace_key, False)
                    logger.info(
                        "job_sync.scheduler.cycle workspace_id=%s boss_paused=%s",
                        workspace_key,
                        boss_paused,
                    )

                    if boss_paused and not previous_paused:
                        logger.warning(
                            "JobSyncScheduler: BOSS sync paused because credentials are expired workspace_id=%s",
                            workspace_key,
                        )
                    if (not boss_paused) and previous_paused:
                        logger.info(
                            "JobSyncScheduler: BOSS sync resumed after credential update workspace_id=%s",
                            workspace_key,
                        )
                    self._boss_paused_by_workspace[workspace_key] = boss_paused

                    if not boss_paused:
                        # 1. Sync & Enrich (Infrastructure)
                        service.execute_due_tasks(limit=settings.job_sync_scheduler_batch_size)
                        get_job_service(session).enrich_candidate_metadata(limit=20)
                        
                        # 2. Recruitment Automation (Business Logic)
                        get_ai_resume_service(session).execute_due_auto_resume_requests()
                        get_ai_resume_service(session).execute_due_resume_access_retries(
                            limit=settings.resume_access_retry_batch_size
                        )

                    # 3. Evaluation (Downstream)
                    get_recruitment_automation_service(session).execute_due_candidate_evaluations(
                        limit=settings.ai_candidate_evaluation_batch_size
                    )

                    session.commit()

                    if settings.job_global_sync_enabled and not boss_paused:
                        now_ts = time.time()
                        interval_sec = settings.job_global_sync_interval_minutes * 60
                        last_run_at = self._last_global_sync_at_by_workspace.get(workspace_key, 0.0)
                        if now_ts - last_run_at >= interval_sec:
                            service.execute_global_job_sync()
                            self._last_global_sync_at_by_workspace[workspace_key] = now_ts
                except CredentialsExpiredError as e:
                    logger.error("JobSyncScheduler: Credentials expired workspace_id=%s error=%s", workspace_key, e)
                    try:
                        error_session = SessionLocal()
                        try:
                            error_session.info["workspace_id"] = context.workspace_id
                            error_session.info["user_id"] = context.owner_user_id
                            get_credential_service(error_session).handle_credential_failure("boss", error_message=str(e))
                            error_session.commit()
                        finally:
                            error_session.close()
                    except Exception as notify_exc:
                        logger.error(
                            "JobSyncScheduler: Failed to handle credential failure workspace_id=%s error=%s",
                            workspace_key,
                            notify_exc,
                        )
                except Exception as e:
                    logger.error("JobSyncScheduler: Unexpected error workspace_id=%s error=%s", workspace_key, e)
                finally:
                    session.close()
            self.stop_event.wait(max(1, settings.job_sync_scheduler_poll_seconds))


def create_job_sync_scheduler() -> JobSyncScheduler:
    return JobSyncScheduler(stop_event=threading.Event())
