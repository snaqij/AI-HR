"""RTC webhook routes for AI interviews."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ...core.config import get_settings
from ...core.responses import Envelope
from ...db.session import get_db_session
from ...schemas.ai_interviews import AIInterviewRTCWebhookResponse
from ...services.ai_interviews import get_ai_interview_service
from ...services.rtc.livekit_webhook import LiveKitWebhookAuthError, verify_livekit_webhook_token

router = APIRouter(prefix="/ai/interviews/rtc/webhooks", tags=["ai-interview-webhooks"])


@router.post("/livekit", response_model=Envelope[AIInterviewRTCWebhookResponse])
async def handle_livekit_webhook(
    request: Request,
    session: Session = Depends(get_db_session),
) -> Envelope[AIInterviewRTCWebhookResponse]:
    settings = get_settings()
    if not settings.ai_interview_rtc_webhook_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="rtc_webhook_disabled")

    claims: dict | None = None
    if settings.livekit_webhook_signature_required:
        expected_api_key = settings.livekit_webhook_api_key or settings.livekit_api_key
        try:
            claims = verify_livekit_webhook_token(
                authorization=request.headers.get("authorization"),
                api_secret=settings.livekit_api_secret or "",
                expected_api_key=expected_api_key,
                accept_skew_seconds=settings.livekit_webhook_accept_skew_seconds,
            )
        except LiveKitWebhookAuthError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    try:
        payload = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_webhook_payload") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_webhook_payload")

    service = get_ai_interview_service(session)
    result = service.rtc_handle_livekit_webhook(
        payload=payload,
        claims=claims or {},
        remote_ip=request.client.host if request.client else None,
    )
    return Envelope.success(AIInterviewRTCWebhookResponse.model_validate(result))
