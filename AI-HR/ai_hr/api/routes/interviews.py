"""面试排期路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ...core.responses import Envelope
from ...db.session import get_db_session
from ...schemas.interviews import (
    InterviewDispatchRequest,
    InterviewDispatchResult,
    InterviewPlanRequest,
    InterviewPlanResult,
    InterviewProgressResult,
    InterviewResponse,
    InterviewScheduleRequest,
    InterviewScheduleResult,
    InterviewSendRequest,
    InterviewSendResult,
    InterviewSyncStatusRequest,
    InterviewSyncStatusResult,
)
from ...services.interviews import get_interview_service

router = APIRouter(prefix="", tags=["interviews"])


@router.post("/interviews/schedule", response_model=Envelope[InterviewScheduleResult], status_code=status.HTTP_201_CREATED)
def schedule_interview(
    payload: InterviewScheduleRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[InterviewScheduleResult]:
    """创建面试排期记录。"""
    service = get_interview_service(session)
    result = service.schedule_interview(payload)
    return Envelope.success(
        InterviewScheduleResult(
            interview=InterviewResponse.model_validate(result["interview"]),
            dispatched=result["dispatched"],
            dispatch_payload=result["dispatch_payload"],
        )
    )


@router.post("/interviews/{interview_id}/dispatch", response_model=Envelope[InterviewDispatchResult])
def dispatch_interview(
    interview_id: str,
    payload: InterviewDispatchRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[InterviewDispatchResult]:
    """执行外部约面。"""
    service = get_interview_service(session)
    result = service.dispatch_interview(interview_id, payload)
    return Envelope.success(
        InterviewDispatchResult(
            interview=InterviewResponse.model_validate(result["interview"]),
            status=result["status"],
            dispatch_payload=result["dispatch_payload"],
        )
    )


@router.post("/interviews/{interview_id}/sync-status", response_model=Envelope[InterviewSyncStatusResult])
def sync_interview_status(
    interview_id: str,
    payload: InterviewSyncStatusRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[InterviewSyncStatusResult]:
    """同步外部约面状态。"""
    service = get_interview_service(session)
    result = service.sync_interview_status(interview_id, payload)
    return Envelope.success(
        InterviewSyncStatusResult(
            interview=InterviewResponse.model_validate(result["interview"]),
            status=result["status"],
            sync_payload=result["sync_payload"],
        )
    )


@router.get("/interviews/{interview_id}", response_model=Envelope[InterviewResponse])
def get_interview(
    interview_id: str,
    session: Session = Depends(get_db_session),
) -> Envelope[InterviewResponse]:
    """查询面试记录。"""
    service = get_interview_service(session)
    interview = service.get_interview(interview_id)
    return Envelope.success(InterviewResponse.model_validate(interview))


@router.post("/jobs/{job_id}/interview/plan", response_model=Envelope[InterviewPlanResult])
def plan_job_interviews(
    job_id: str,
    payload: InterviewPlanRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[InterviewPlanResult]:
    """按岗位与人数生成可发送邀约计划。"""
    service = get_interview_service(session)
    result = service.plan_interviews(job_id, payload)
    return Envelope.success(InterviewPlanResult.model_validate(result))


@router.post("/jobs/{job_id}/interview/send", response_model=Envelope[InterviewSendResult])
def send_job_interviews(
    job_id: str,
    payload: InterviewSendRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[InterviewSendResult]:
    """按计划批量创建并派发面试邀约。"""
    service = get_interview_service(session)
    result = service.send_interviews(job_id, payload)
    return Envelope.success(InterviewSendResult.model_validate(result))


@router.get("/jobs/{job_id}/interview/progress", response_model=Envelope[InterviewProgressResult])
def get_job_interview_progress(
    job_id: str,
    session: Session = Depends(get_db_session),
) -> Envelope[InterviewProgressResult]:
    """查询岗位面试邀约进度。"""
    service = get_interview_service(session)
    result = service.get_job_interview_progress(job_id)
    return Envelope.success(InterviewProgressResult.model_validate(result))
