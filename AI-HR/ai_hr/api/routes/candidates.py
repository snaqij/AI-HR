"""候选人管理路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ...core.responses import Envelope
from ...db.session import get_db_session
from ...schemas.ai_resume import (
    CandidateResumeProfileResult,
    ResumeAccessSyncRequest,
    ResumeAccessSyncResult,
    ResumeAttachmentSyncRequest,
    ResumeAttachmentSyncResult,
)
from ...schemas.candidates import (
    CandidateImportRequest,
    CandidateImportResult,
    CandidateResponse,
    CandidateScoreRequest,
    CandidateScoreResult,
)
from ...services.ai_resume import get_ai_resume_service
from ...services.candidates import get_candidate_service

router = APIRouter(prefix="/candidates", tags=["candidates"])


@router.post("/import", response_model=Envelope[CandidateImportResult], status_code=status.HTTP_201_CREATED)
def import_candidates(
    payload: CandidateImportRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[CandidateImportResult]:
    """批量导入候选人并执行去重更新。"""
    service = get_candidate_service(session)
    result = service.import_candidates(payload)
    response = CandidateImportResult(
        created_count=result["created_count"],
        updated_count=result["updated_count"],
        candidates=[CandidateResponse.model_validate(item) for item in result["candidates"]],
    )
    return Envelope.success(response)


@router.post("/{candidate_id}/score", response_model=Envelope[CandidateScoreResult])
def score_candidate(
    candidate_id: str,
    payload: CandidateScoreRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[CandidateScoreResult]:
    """对指定候选人执行评分并回写结果。"""
    service = get_candidate_service(session)
    result = service.score_candidate(candidate_id, payload)
    response = CandidateScoreResult(
        candidate=CandidateResponse.model_validate(result["candidate"]),
        total_score=result["total_score"],
        dimensions=result["dimensions"],
        explanation=result["explanation"],
    )
    return Envelope.success(response)


@router.get("/{candidate_id}/resume-profile", response_model=Envelope[CandidateResumeProfileResult])
def get_candidate_resume_profile(
    candidate_id: str,
    session: Session = Depends(get_db_session),
) -> Envelope[CandidateResumeProfileResult]:
    """查询候选人的结构化简历画像。"""
    service = get_ai_resume_service(session)
    result = service.get_candidate_resume_profile(candidate_id)
    return Envelope.success(result)


@router.post("/{candidate_id}/resume-attachment/sync", response_model=Envelope[ResumeAttachmentSyncResult])
def sync_candidate_resume_attachment(
    candidate_id: str,
    session: Session = Depends(get_db_session),
) -> Envelope[ResumeAttachmentSyncResult]:
    """从 BOSS 拉取候选人附件简历并保存到本地。"""
    service = get_ai_resume_service(session)
    result = service.sync_resume_attachment(ResumeAttachmentSyncRequest(candidate_id=candidate_id))
    return Envelope.success(result)


@router.post("/{candidate_id}/resume-access/sync", response_model=Envelope[ResumeAccessSyncResult])
def sync_candidate_resume_access(
    candidate_id: str,
    session: Session = Depends(get_db_session),
) -> Envelope[ResumeAccessSyncResult]:
    """向 BOSS 申请候选人附件简历，并在可用时立即下载。"""
    service = get_ai_resume_service(session)
    result = service.sync_resume_access(ResumeAccessSyncRequest(candidate_id=candidate_id))
    return Envelope.success(result)
