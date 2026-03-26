"""岗位管理路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ...core.responses import Envelope
from ...db.session import get_db_session
from ...schemas.ai_scoring import JobShortlistResult
from ...schemas.jobs import (
    JobCandidateSyncRequest,
    JobCandidateSyncResult,
    JobCreateRequest,
    JobPublishRequest,
    JobPublishResult,
    JobPublishStatusResponse,
    JobResponse,
)
from ...services.jobs import get_job_service
from ...services.ai_scoring import get_ai_scoring_service

router = APIRouter(prefix="/jobs", tags=["jobs"])


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
    service = get_job_service(session)
    result = service.sync_candidates(job_id, payload)
    response = JobCandidateSyncResult(
        job_id=result["job_id"],
        total_pulled=result["total_pulled"],
        total_created=result["total_created"],
        total_updated=result["total_updated"],
        channels=result["channels"],
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
