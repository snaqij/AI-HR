"""Job management routes."""

from __future__ import annotations
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from ...core.auth_dependencies import require_workspace_context
from ...core.exceptions import InvalidStateError, ResourceNotFoundError
from ...core.responses import Envelope
from ...db.session import get_db_session
from ...schemas.ai_resume import (
    ResumeAccessBatchSyncRequest,
    ResumeAccessBatchSyncResult,
    ResumeAttachmentBatchSyncRequest,
    ResumeAttachmentBatchSyncResult,
)
from ...schemas.ai_scoring import JobShortlistResult
from ...schemas.candidate_evaluations import (
    CandidateEvaluationDetailResult,
    CandidateEvaluationListResult,
    CandidateEvaluationRequest,
    CandidateEvaluationUpdateRequest,
)
from ...schemas.interview_invitation_email import (
    CandidateEmailDeliveryListResult,
    InterviewInvitationEmailSendRequest,
    InterviewInvitationEmailSendResult,
)
from ...schemas.job_sync import (
    JobSyncRunListResult,
    JobSyncRunResponse,
    JobSyncTaskExecuteResult,
    JobSyncTaskListResult,
    JobSyncTaskResponse,
    JobSyncTaskUpsertRequest,
)
from ...schemas.jobs import (
    JobBatchDeleteRequest,
    JobBatchDeleteResult,
    JobCandidateItem,
    JobCandidateListResult,
    JobCandidateStageUpdateRequest,
    JobCandidateSyncRequest,
    JobCandidateSyncResult,
    JobCreateRequest,
    JobListResult,
    JobPublishRequest,
    JobPublishResult,
    JobPublishStatusResponse,
    JobResumeReadySyncRequest,
    JobResumeReadySyncResult,
    JobResponse,
    JobUpdateSettingsRequest,
    RemoteJobImportRequest,
    RemoteJobImportResult,
    RemoteJobListItem,
    RemoteJobListResult,
)
from ...services.ai_scoring import get_ai_scoring_service
from ...services.ai_resume import get_ai_resume_service
from ...services.candidate_evaluations import get_candidate_evaluation_service
from ...services.interview_invitation_email import get_interview_invitation_email_service
from ...services.job_sync import get_job_sync_service
from ...services.jobs import get_job_service

router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(require_workspace_context)])


@router.post("", response_model=Envelope[JobResponse], status_code=status.HTTP_201_CREATED)
def create_job(
    payload: JobCreateRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[JobResponse]:
    """创建岗位。"""
    service = get_job_service(session)
    job = service.create_job(payload)
    return Envelope.success(JobResponse.model_validate(job))


@router.get("/{job_id}", response_model=Envelope[JobResponse])
def get_job(
    job_id: str,
    session: Session = Depends(get_db_session),
) -> Envelope[JobResponse]:
    """查询岗位详情。"""
    service = get_job_service(session)
    job = service.get_job(job_id)
    return Envelope.success(JobResponse.model_validate(job))


@router.patch("/{job_id}/settings", response_model=Envelope[JobResponse])
def update_job_settings(
    job_id: str,
    payload: JobUpdateSettingsRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[JobResponse]:
    """更新岗位自动化配置（如学历、经验门槛）。"""
    service = get_job_service(session)
    job = service.update_job_settings(job_id, payload)
    return Envelope.success(JobResponse.model_validate(job))


@router.get("", response_model=Envelope[JobListResult])
def list_jobs(
    limit: int = 20,
    offset: int = 0,
    platform: str | None = None,
    name: str | None = None,
    job_type: str | None = None,
    salary: str | None = None,
    session: Session = Depends(get_db_session),
) -> Envelope[JobListResult]:
    """列出全量已创建/同步的岗位。"""
    service = get_job_service(session)
    jobs = service.list_jobs(
        limit=limit,
        offset=offset,
        platform=platform,
        name=name,
        job_type=job_type,
        salary=salary,
    )
    return Envelope.success(
        JobListResult(
            total=len(jobs),
            items=[JobResponse.model_validate(item) for item in jobs],
        )
    )


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(
    job_id: str,
    session: Session = Depends(get_db_session),
) -> None:
    """Delete one job."""
    service = get_job_service(session)
    service.delete_job(job_id)


@router.post("/batch-delete", response_model=Envelope[JobBatchDeleteResult])
def batch_delete_jobs(
    payload: JobBatchDeleteRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[JobBatchDeleteResult]:
    """Batch delete jobs."""
    service = get_job_service(session)
    deleted_count = service.batch_delete_jobs(payload.job_ids)
    return Envelope.success(JobBatchDeleteResult(deleted_count=deleted_count))


@router.post("/{job_id}/publish", response_model=Envelope[JobPublishResult])
def publish_job(
    job_id: str,
    payload: JobPublishRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[JobPublishResult]:
    """发布岗位到指定渠道。"""
    service = get_job_service(session)
    job = service.publish_job(job_id, payload)
    result = JobPublishResult(
        job=JobResponse.model_validate(job),
        publications=[publication for publication in JobResponse.model_validate(job).publications],
    )
    return Envelope.success(result)


@router.get("/{job_id}/publish-status", response_model=Envelope[JobPublishStatusResponse])
def get_publish_status(
    job_id: str,
    session: Session = Depends(get_db_session),
) -> Envelope[JobPublishStatusResponse]:
    """同步并返回岗位发布状态。"""
    service = get_job_service(session)
    publish_status = service.get_publish_status(job_id)
    response = JobPublishStatusResponse(
        job_id=publish_status["job_id"],
        publications=publish_status["publications"],
    )
    return Envelope.success(response)


@router.post("/{job_id}/candidates/sync", response_model=Envelope[JobCandidateSyncResult])
def sync_job_candidates(
    job_id: str,
    payload: JobCandidateSyncRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[JobCandidateSyncResult]:
    """按岗位从渠道拉取候选人并增量同步。"""
    service = get_job_sync_service(session)
    result = service.run_manual_sync(job_id, payload)
    response = JobCandidateSyncResult(
        job_id=result["job_id"],
        total_pulled=result["total_pulled"],
        total_created=result["total_created"],
        total_updated=result["total_updated"],
        channels=result["channels"],
        resume_access=result.get("resume_access"),
    )
    return Envelope.success(response)


@router.post("/{job_id}/resume-ready-candidates/sync", response_model=Envelope[JobResumeReadySyncResult])
def sync_job_resume_ready_candidates(
    job_id: str,
    payload: JobResumeReadySyncRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[JobResumeReadySyncResult]:
    """同步岗位下已获得简历的候选人池。"""
    service = get_job_service(session)
    result = service.sync_resume_ready_candidates(job_id, payload)
    return Envelope.success(result)


@router.put("/{job_id}/sync-task", response_model=Envelope[JobSyncTaskResponse])
def upsert_job_sync_task(
    job_id: str,
    payload: JobSyncTaskUpsertRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[JobSyncTaskResponse]:
    """创建或更新岗位定时同步任务。"""
    service = get_job_sync_service(session)
    task = service.upsert_task(job_id, payload)
    return Envelope.success(JobSyncTaskResponse.model_validate(task))


@router.get("/{job_id}/sync-tasks", response_model=Envelope[JobSyncTaskListResult])
def list_job_sync_tasks(
    job_id: str,
    session: Session = Depends(get_db_session),
) -> Envelope[JobSyncTaskListResult]:
    """查询岗位定时同步任务。"""
    service = get_job_sync_service(session)
    tasks = service.list_tasks(job_id)
    return Envelope.success(
        JobSyncTaskListResult(
            job_id=job_id,
            tasks=[JobSyncTaskResponse.model_validate(item) for item in tasks],
        )
    )


@router.get("/{job_id}/sync-runs", response_model=Envelope[JobSyncRunListResult])
def list_job_sync_runs(
    job_id: str,
    limit: int = 20,
    session: Session = Depends(get_db_session),
) -> Envelope[JobSyncRunListResult]:
    """查询岗位同步执行流水。"""
    service = get_job_sync_service(session)
    runs = service.list_runs(job_id, limit=limit)
    return Envelope.success(
        JobSyncRunListResult(
            job_id=job_id,
            runs=[JobSyncRunResponse.model_validate(item) for item in runs],
        )
    )


@router.post("/sync-tasks/{task_id}/run", response_model=Envelope[JobSyncTaskExecuteResult])
def run_job_sync_task(
    task_id: str,
    session: Session = Depends(get_db_session),
) -> Envelope[JobSyncTaskExecuteResult]:
    """手动触发一次定时同步任务。"""
    service = get_job_sync_service(session)
    result = service.execute_task(task_id)
    response = JobSyncTaskExecuteResult(
        task=JobSyncTaskResponse.model_validate(result["task"]),
        run=JobSyncRunResponse.model_validate(result["run"]),
        summary=result["summary"],
    )
    return Envelope.success(response)


@router.get("/{job_id}/candidates", response_model=Envelope[JobCandidateListResult])
def list_job_candidates(
    job_id: str,
    limit: int = 30,
    cursor: str | None = None,
    keyword: str | None = None,
    resume_status: str | None = None,
    stage: str | None = None,
    segment: str | None = None,
    session: Session = Depends(get_db_session),
) -> Envelope[JobCandidateListResult]:
    """查看岗位下已同步的候选人。"""
    service = get_job_service(session)
    result = service.list_job_candidates(
        job_id,
        limit=limit,
        cursor=cursor,
        keyword=keyword,
        resume_status=resume_status,
        stage=stage,
        segment=segment,
    )
    response = JobCandidateListResult(
        job_id=result["job_id"],
        total=result["total"],
        evaluated_count=result["evaluated_count"],
        sent_count=result["sent_count"],
        limit=result["limit"],
        next_cursor=result["next_cursor"],
        has_more=result["has_more"],
        candidates=[
            JobCandidateItem(
                candidate=item["candidate"],
                channel=item["channel"],
                external_candidate_id=item["external_candidate_id"],
                external_job_id=item["external_job_id"],
                stage=item["stage"],
                source_status=item["source_status"],
                applied_at=item.get("applied_at"),
                first_synced_at=item["first_synced_at"],
                last_synced_at=item["last_synced_at"],
                source_payload=item["source_payload"],
                resume_request_status=item.get("resume_request_status"),
                resume_download_status=item.get("resume_download_status"),
                last_resume_requested_at=item.get("last_resume_requested_at"),
                evaluation=item.get("evaluation"),
                latest_delivery=item.get("latest_delivery"),
            )
            for item in result["candidates"]
        ],
    )
    return Envelope.success(response)


@router.get("/{job_id}/candidates/{candidate_id}", response_model=Envelope[JobCandidateItem])
def get_job_candidate(
    job_id: str,
    candidate_id: str,
    session: Session = Depends(get_db_session),
) -> Envelope[JobCandidateItem]:
    """Get one candidate under a job."""
    service = get_job_service(session)
    item = service.get_job_candidate(job_id, candidate_id)
    response = JobCandidateItem(
        candidate=item.candidate,
        channel=item.channel,
        external_candidate_id=item.external_candidate_id,
        external_job_id=item.external_job_id,
        stage=item.stage,
        source_status=item.source_status,
        applied_at=item.applied_at,
        first_synced_at=item.first_synced_at,
        last_synced_at=item.last_synced_at,
        source_payload={},
        resume_request_status=item.pipeline.resume_request_status if item.pipeline else None,
        resume_download_status=item.pipeline.resume_download_status if item.pipeline else None,
        last_resume_requested_at=item.pipeline.last_resume_requested_at if item.pipeline else None,
        evaluation=item.evaluation,
        latest_delivery=item.latest_delivery,
    )
    return Envelope.success(response)


@router.post("/{job_id}/candidates/{candidate_id}/link", response_model=Envelope[JobCandidateItem])
def link_job_candidate(
    job_id: str,
    candidate_id: str,
    session: Session = Depends(get_db_session),
) -> Envelope[JobCandidateItem]:
    """Create a local job-candidate link for imported candidates."""
    service = get_job_service(session)
    item = service.link_candidate(job_id, candidate_id)
    response = JobCandidateItem(
        candidate=item.candidate,
        channel=item.channel,
        external_candidate_id=item.external_candidate_id,
        external_job_id=item.external_job_id,
        stage=item.stage,
        source_status=item.source_status,
        applied_at=item.applied_at,
        first_synced_at=item.first_synced_at,
        last_synced_at=item.last_synced_at,
        source_payload={},
        resume_request_status=item.pipeline.resume_request_status if item.pipeline else None,
        resume_download_status=item.pipeline.resume_download_status if item.pipeline else None,
        last_resume_requested_at=item.pipeline.last_resume_requested_at if item.pipeline else None,
        evaluation=item.evaluation,
        latest_delivery=item.latest_delivery,
    )
    return Envelope.success(response)


@router.patch("/{job_id}/candidates/{candidate_id}", response_model=Envelope[JobCandidateItem])
def update_job_candidate_stage(
    job_id: str,
    candidate_id: str,
    payload: JobCandidateStageUpdateRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[JobCandidateItem]:
    """更新岗位下候选人的招聘阶段。"""
    service = get_job_service(session)
    item = service.update_candidate_stage(job_id, candidate_id, payload.stage)
    response = JobCandidateItem(
        candidate=item.candidate,
        channel=item.channel,
        external_candidate_id=item.external_candidate_id,
        external_job_id=item.external_job_id,
        stage=item.stage,
        source_status=item.source_status,
        first_synced_at=item.first_synced_at,
        last_synced_at=item.last_synced_at,
        source_payload=item.source_payload,
    )
    return Envelope.success(response)


@router.post("/{job_id}/resume-attachments/sync", response_model=Envelope[ResumeAttachmentBatchSyncResult])
def sync_job_resume_attachments(
    job_id: str,
    payload: ResumeAttachmentBatchSyncRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[ResumeAttachmentBatchSyncResult]:
    """批量同步岗位下候选人的附件简历。"""
    service = get_ai_resume_service(session)
    result = service.sync_job_resume_attachments(job_id, payload)
    return Envelope.success(result)


@router.post("/{job_id}/resume-access/sync", response_model=Envelope[ResumeAccessBatchSyncResult])
def sync_job_resume_access(
    job_id: str,
    payload: ResumeAccessBatchSyncRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[ResumeAccessBatchSyncResult]:
    """批量申请岗位下候选人的附件简历，并在可用时下载。"""
    service = get_ai_resume_service(session)
    result = service.sync_job_resume_access(job_id, payload)
    return Envelope.success(result)


@router.post(
    "/{job_id}/candidates/{candidate_id}/evaluate",
    response_model=Envelope[CandidateEvaluationDetailResult],
)
def evaluate_job_candidate(
    job_id: str,
    candidate_id: str,
    payload: CandidateEvaluationRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[CandidateEvaluationDetailResult]:
    """Evaluate a candidate in detail against a specific job."""
    service = get_candidate_evaluation_service(session)
    result = service.evaluate_candidate(job_id=job_id, candidate_id=candidate_id, payload=payload)
    return Envelope.success(result)


@router.get("/{job_id}/evaluations", response_model=Envelope[CandidateEvaluationListResult])
def list_job_evaluations(
    job_id: str,
    limit: int = 100,
    offset: int = 0,
    candidate_ids: str | None = None,
    session: Session = Depends(get_db_session),
) -> Envelope[CandidateEvaluationListResult]:
    """List detailed candidate evaluations under a job."""
    service = get_candidate_evaluation_service(session)
    ids = [item.strip() for item in (candidate_ids or "").split(",") if item.strip()]
    result = service.list_job_evaluations(
        job_id=job_id,
        limit=limit,
        offset=offset,
        candidate_ids=ids or None,
    )
    return Envelope.success(result)


@router.get(
    "/{job_id}/candidates/{candidate_id}/evaluation-latest",
    response_model=Envelope[CandidateEvaluationDetailResult],
)
def get_latest_job_candidate_evaluation(
    job_id: str,
    candidate_id: str,
    session: Session = Depends(get_db_session),
) -> Envelope[CandidateEvaluationDetailResult]:
    """Get the latest detailed evaluation for a candidate under a job."""
    service = get_candidate_evaluation_service(session)
    result = service.get_latest_job_candidate_evaluation(job_id=job_id, candidate_id=candidate_id)
    return Envelope.success(result)


@router.patch(
    "/{job_id}/candidates/{candidate_id}/evaluation-latest",
    response_model=Envelope[CandidateEvaluationDetailResult],
)
def update_latest_job_candidate_evaluation(
    job_id: str,
    candidate_id: str,
    payload: CandidateEvaluationUpdateRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[CandidateEvaluationDetailResult]:
    """Manually update the latest detailed evaluation for a candidate under a job."""
    service = get_candidate_evaluation_service(session)
    result = service.update_latest_job_candidate_evaluation(
        job_id=job_id,
        candidate_id=candidate_id,
        payload=payload,
    )
    return Envelope.success(result)


@router.post(
    "/{job_id}/candidates/{candidate_id}/invite-email",
    response_model=Envelope[InterviewInvitationEmailSendResult],
)
def send_candidate_invitation_email(
    job_id: str,
    candidate_id: str,
    payload: InterviewInvitationEmailSendRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[InterviewInvitationEmailSendResult]:
    """Manually send an interview invitation email to a candidate."""
    service = get_interview_invitation_email_service(session)
    try:
        result = service.send_manual_invitation(
            job_id=job_id,
            candidate_id=candidate_id,
            evaluation_id=payload.evaluation_id,
            template_code=payload.template_code,
            note=payload.note,
        )
    except (InvalidStateError, ResourceNotFoundError) as exc:
        return Envelope.failure("invite_email_failed", str(exc))
    return Envelope.success(InterviewInvitationEmailSendResult(**result))


@router.get("/{job_id}/email-deliveries", response_model=Envelope[CandidateEmailDeliveryListResult])
def list_job_email_deliveries(
    job_id: str,
    candidate_id: str | None = None,
    limit: int = 100,
    session: Session = Depends(get_db_session),
) -> Envelope[CandidateEmailDeliveryListResult]:
    """List invitation email delivery records for a job."""
    service = get_interview_invitation_email_service(session)
    result = service.list_job_email_deliveries(job_id=job_id, candidate_id=candidate_id, limit=limit)
    return Envelope.success(result)


@router.get("/remote/{channel}", response_model=Envelope[RemoteJobListResult])
def list_remote_jobs(
    channel: str,
    page: int = 1,
    page_size: int = 20,
    session: Session = Depends(get_db_session),
) -> Envelope[RemoteJobListResult]:
    """查看渠道侧已发布岗位。"""
    service = get_job_service(session)
    result = service.list_remote_jobs(channel=channel, page=page, page_size=page_size)
    response = RemoteJobListResult(
        channel=result["channel"],
        page=result["page"],
        page_size=result["page_size"],
        jobs=[RemoteJobListItem(**item) for item in result["jobs"]],
    )
    return Envelope.success(response)


@router.post("/remote/import", response_model=Envelope[RemoteJobImportResult])
def import_remote_jobs(
    payload: RemoteJobImportRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[RemoteJobImportResult]:
    """将渠道侧已发布岗位导入本地。"""
    service = get_job_service(session)
    result = service.import_remote_jobs(channel=payload.channel, page=payload.page, page_size=payload.page_size)
    response = RemoteJobImportResult(
        channel=result["channel"],
        created_count=result["created_count"],
        updated_count=result["updated_count"],
        jobs=[JobResponse.model_validate(item) for item in result["jobs"]],
    )
    return Envelope.success(response)


@router.get("/{job_id}/shortlist", response_model=Envelope[JobShortlistResult])
def get_job_shortlist(
    job_id: str,
    session: Session = Depends(get_db_session),
) -> Envelope[JobShortlistResult]:
    """查询岗位 AI 入围名单。"""
    service = get_ai_scoring_service(session)
    result = service.get_job_shortlist(job_id)
    return Envelope.success(result)
