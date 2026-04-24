"""AI 面试邀请 API 路由。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core.responses import Envelope
from ...db.session import get_db_session
from ...schemas.ai_interviews import (
    AIInterviewInvitationCreateRequest,
    AIInterviewInvitationResponse,
)
from ...services.ai_interviews import get_ai_interview_service

router = APIRouter(prefix="/ai-interviews/invitations", tags=["ai_interview_invitation"])


@router.post("", response_model=Envelope[AIInterviewInvitationResponse])
async def create_invitation(
    payload: AIInterviewInvitationCreateRequest,
    db: Session = Depends(get_db_session),
):
    """创建面试邀请链接。"""
    service = get_ai_interview_service(db)
    result = service.create_invitation(
        candidate_id=payload.candidate_id,
        job_id=payload.job_id,
        note=payload.note,
    )
    return Envelope.success(result)


@router.get("/token/{token}", response_model=Envelope[AIInterviewInvitationResponse])
async def get_invitation_by_token(
    token: str,
    db: Session = Depends(get_db_session),
):
    """通过 Token 获取邀请详情。"""
    service = get_ai_interview_service(db)
    result = service.get_invitation_by_token(token)
    return Envelope.success(result)


@router.post("/token/{token}/activate", response_model=Envelope[dict])
async def activate_invitation(
    token: str,
    db: Session = Depends(get_db_session),
):
    """通过邀请链接激活并开始面试。"""
    service = get_ai_interview_service(db)
    result = service.activate_invitation(token)
    return Envelope.success(result)
