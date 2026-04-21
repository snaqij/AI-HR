"""岗位候选人同步调度与执行服务。"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.exceptions import ConnectorOperationError, CredentialsExpiredError
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
        try:
            result = self._job_service.sync_candidates(job_id, payload)
            result["resume_access"] = self._maybe_sync_resume_access(job_id, payload, result)
            run = self._run_repository.complete(
                run.id,
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
            self._run_repository.complete(
                run.id,
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
                entity_id=run.id,
                status="failed",
                job_id=job_id,
                channel=primary_channel,
                payload={"error": str(exc)},
            )
            raise

    def execute_task(self, task_id: str):
        task = self._task_repository.get(task_id)
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
        try:
            result = self._job_service.sync_candidates(task.job_id, payload)
            result["resume_access"] = self._maybe_sync_resume_access(task.job_id, payload, result)
            run = self._run_repository.complete(
                run.id,
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
            return {"task": task, "run": run, "summary": result}
        except Exception as exc:
            task = self._task_repository.mark_result(
                task.id,
                status="failed",
                error_message=str(exc),
                next_run_at=compute_next_run_at(task.interval_minutes),
                clear_reset_cursor=False,
            )
            run = self._run_repository.complete(
                run.id,
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
                entity_id=run.id,
                status="failed",
                job_id=task.job_id,
                channel=task.channel,
                payload={"error": str(exc)},
            )
            raise

    def execute_due_tasks(self, limit: int | None = None) -> list[dict]:
        now = datetime.now(UTC).replace(tzinfo=None)
        due_tasks = self._task_repository.list_due(
            now=now,
            limit=limit or self._settings.job_sync_scheduler_batch_size,
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
        channels = ["boss"]  # 目前仅支持 boss，后续可扩展
        results = []
        for channel in channels:
            try:
                res = self._job_service.import_remote_jobs(
                    channel=channel, 
                    page=1, 
                    page_size=self._settings.job_global_sync_max_pages * 20
                )
                results.append(res)
            except Exception as e:
                logger.exception("job_sync.global_sync.failed channel=%s", channel)
        return results

    def _maybe_sync_resume_access(
        self,
        job_id: str,
        payload: JobCandidateSyncRequest,
        sync_result: dict,
    ):
        if not (payload.auto_request_resume or payload.auto_sync_resume_attachment):
            return None
        candidate_ids = list(dict.fromkeys(sync_result.get("synced_candidate_ids", [])))
        if not candidate_ids:
            return None
        result = self._ai_resume_service.sync_job_resume_access(
            job_id,
            ResumeAccessBatchSyncRequest(
                candidate_ids=candidate_ids,
                sync_attachment_when_ready=payload.auto_sync_resume_attachment,
            ),
        )
        return result.model_dump(mode="json")


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
    _last_global_sync_at: float = 0.0

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

    def _run_loop(self) -> None:
        settings = get_settings()
        while not self.stop_event.is_set():
            session = SessionLocal()
            try:
                service = get_job_sync_service(session)
                # 1. 候选人增量同步
                service.execute_due_tasks(limit=settings.job_sync_scheduler_batch_size)
                
                # 2. 简历附件下载重试
                get_ai_resume_service(session).execute_due_resume_access_retries(
                    limit=settings.resume_access_retry_batch_size
                )

                # 3. 简历下载完成后自动评估
                get_recruitment_automation_service(session).execute_due_candidate_evaluations(
                    limit=settings.ai_candidate_evaluation_batch_size
                )

                # 4. 达标候选人自动发送面试邀请邮件 (暂时注释掉，只保留到评估分析)
                # get_recruitment_automation_service(session).execute_due_invitation_emails(
                #     limit=settings.ai_auto_invitation_batch_size
                # )

                # 3. 补全元数据 (后台执行)
                get_job_service(session).enrich_candidate_metadata(limit=5)

                # 4. 自动发起简历请求 (自动伯乐流水线)
                get_ai_resume_service(session).execute_due_auto_resume_requests()

                session.commit()

                # 6. 全局岗位发现同步 (Timed Sync)
                if settings.job_global_sync_enabled:
                    now_ts = time.time()
                    interval_sec = settings.job_global_sync_interval_minutes * 60
                    if now_ts - self._last_global_sync_at >= interval_sec:
                        service.execute_global_job_sync()
                        self._last_global_sync_at = now_ts
            except CredentialsExpiredError as e:
                # Handle credential expiration by notifying admin
                logger.error(f"JobSyncScheduler: Credentials expired: {e}")
                try:
                    # We need a new session to handle the error properly
                    error_session = SessionLocal()
                    try:
                        get_credential_service(error_session).handle_credential_failure("boss", error_message=str(e))
                        error_session.commit()
                    finally:
                        error_session.close()
                except Exception as notify_exc:
                    logger.error(f"JobSyncScheduler: Failed to handle credential failure: {notify_exc}")
            except Exception as e:
                logger.error(f"JobSyncScheduler: Unexpected error: {e}")
            finally:
                session.close()
            self.stop_event.wait(max(1, settings.job_sync_scheduler_poll_seconds))


def create_job_sync_scheduler() -> JobSyncScheduler:
    return JobSyncScheduler(stop_event=threading.Event())
