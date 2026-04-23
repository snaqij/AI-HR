"""Enterprise AI assessment routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...core.auth_dependencies import require_workspace_context
from ...core.responses import Envelope
from ...db.session import get_db_session
from ...schemas.ai_assessments import (
    CompositeAssessmentComputeRequest,
    CompositeAssessmentComputeResponse,
    CompositeDecisionRequest,
    CompositeDecisionResponse,
    CompositeOverrideRequest,
    CompositeOverrideResponse,
    InterviewAssessmentComputeRequest,
    InterviewAssessmentComputeResponse,
    InterviewAssessmentLatestResponse,
    PipelineNextStepPublishRequest,
    PipelineNextStepPublishResponse,
    ReviewQueueTaskListResponse,
)
from ...services.enterprise_assessment import get_enterprise_assessment_service

router = APIRouter(prefix="", tags=["ai-assessments"], dependencies=[Depends(require_workspace_context)])


@router.post(
    "/ai/interviews/sessions/{session_id}/assessments/compute",
    response_model=Envelope[InterviewAssessmentComputeResponse],
)
def compute_interview_assessment(
    session_id: str,
    payload: InterviewAssessmentComputeRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[InterviewAssessmentComputeResponse]:
    service = get_enterprise_assessment_service(session)
    assessment, queue_id = service.compute_interview_assessment(
        session_id=session_id,
        run_mode=payload.run_mode,
        policy_code=payload.policy_code,
        policy_version=payload.policy_version,
        force_recompute=payload.force_recompute,
    )
    return Envelope.success(
        InterviewAssessmentComputeResponse(
            assessment_id=assessment.id,
            status=assessment.status,
            queue_id=queue_id,
            eta_ms=0,
        )
    )


@router.get(
    "/ai/interviews/sessions/{session_id}/assessments/latest",
    response_model=Envelope[InterviewAssessmentLatestResponse],
)
def get_latest_interview_assessment(
    session_id: str,
    session: Session = Depends(get_db_session),
) -> Envelope[InterviewAssessmentLatestResponse]:
    service = get_enterprise_assessment_service(session)
    return Envelope.success(service.get_latest_interview_assessment_response(session_id=session_id))


@router.post(
    "/ai/composite-assessments/compute",
    response_model=Envelope[CompositeAssessmentComputeResponse],
)
def compute_composite_assessment(
    payload: CompositeAssessmentComputeRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[CompositeAssessmentComputeResponse]:
    service = get_enterprise_assessment_service(session)
    assessment = service.compute_composite_assessment(payload)
    return Envelope.success(
        CompositeAssessmentComputeResponse(
            composite_assessment_id=assessment.id,
            resume_score=float(assessment.resume_score),
            interview_score=float(assessment.interview_score),
            market_score=float(assessment.market_score),
            composite_score=float(assessment.final_score),
            status=assessment.status,
        )
    )


@router.post(
    "/ai/composite-assessments/{assessment_id}/decide",
    response_model=Envelope[CompositeDecisionResponse],
)
def decide_composite_assessment(
    assessment_id: str,
    payload: CompositeDecisionRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[CompositeDecisionResponse]:
    service = get_enterprise_assessment_service(session)
    result = service.decide_composite_assessment(
        composite_assessment_id=assessment_id,
        payload=payload,
    )
    return Envelope.success(result)


@router.post(
    "/ai/composite-assessments/{assessment_id}/override",
    response_model=Envelope[CompositeOverrideResponse],
)
def override_composite_decision(
    assessment_id: str,
    payload: CompositeOverrideRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[CompositeOverrideResponse]:
    service = get_enterprise_assessment_service(session)
    result = service.override_decision(
        composite_assessment_id=assessment_id,
        payload=payload,
    )
    return Envelope.success(result)


@router.get(
    "/ai/review-queue/tasks",
    response_model=Envelope[ReviewQueueTaskListResponse],
)
def list_review_queue_tasks(
    status: str | None = Query(default=None),
    priority: int | None = Query(default=None, ge=0, le=100),
    assignee: str | None = Query(default=None),
    job_id: str | None = Query(default=None),
    session: Session = Depends(get_db_session),
) -> Envelope[ReviewQueueTaskListResponse]:
    service = get_enterprise_assessment_service(session)
    result = service.list_review_queue_tasks(
        status=status,
        priority=priority,
        assignee=assignee,
        job_id=job_id,
    )
    return Envelope.success(result)


@router.post(
    "/pipelines/{pipeline_id}/next-step/publish",
    response_model=Envelope[PipelineNextStepPublishResponse],
)
def publish_pipeline_next_step(
    pipeline_id: str,
    payload: PipelineNextStepPublishRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[PipelineNextStepPublishResponse]:
    service = get_enterprise_assessment_service(session)
    next_step_status, published_at = service.publish_next_step(
        pipeline_id=pipeline_id,
        assessment_id=payload.assessment_id,
        expected_version=payload.expected_version,
    )
    return Envelope.success(
        PipelineNextStepPublishResponse(next_step_status=next_step_status, published_at=published_at)
    )
