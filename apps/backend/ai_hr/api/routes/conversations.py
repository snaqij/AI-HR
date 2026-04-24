"""会话自动化路由。"""

from __future__ import annotations
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from ...core.auth_dependencies import require_workspace_context
from ...core.responses import Envelope
from ...db.session import get_db_session
from ...schemas.conversations import (
    ConversationGreetRequest,
    ConversationGreetResult,
    ConversationMessage,
    ConversationReplyRequest,
    ConversationReplyResult,
    ConversationResponse,
    ConversationSyncRequest,
    ConversationSyncResult,
)
from ...services.conversations import get_conversation_service

router = APIRouter(prefix="/conversations", tags=["conversations"], dependencies=[Depends(require_workspace_context)])


@router.post("/greet", response_model=Envelope[ConversationGreetResult], status_code=status.HTTP_201_CREATED)
def greet_candidate(
    payload: ConversationGreetRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[ConversationGreetResult]:
    """向候选人发起打招呼并创建会话。"""
    service = get_conversation_service(session)
    result = service.greet(payload)
    response = ConversationGreetResult(
        conversation=ConversationResponse.model_validate(result["conversation"]),
        dispatched=result["dispatched"],
        dispatch_payload=result["dispatch_payload"],
    )
    return Envelope.success(response)


@router.post("/{conversation_id}/sync", response_model=Envelope[ConversationSyncResult])
def sync_conversation_messages(
    conversation_id: str,
    payload: ConversationSyncRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[ConversationSyncResult]:
    """同步会话消息并更新游标。"""
    service = get_conversation_service(session)
    result = service.sync_messages(conversation_id, payload)
    response = ConversationSyncResult(
        conversation=ConversationResponse.model_validate(result["conversation"]),
        pulled_count=result["pulled_count"],
        next_cursor=result["next_cursor"],
        has_more=result["has_more"],
        messages=[ConversationMessage.model_validate(item) for item in result["messages"]],
    )
    return Envelope.success(response)


@router.post("/reply", response_model=Envelope[ConversationReplyResult])
def reply_conversation(
    payload: ConversationReplyRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[ConversationReplyResult]:
    """执行手动或自动回复。"""
    service = get_conversation_service(session)
    result = service.reply(payload)
    response = ConversationReplyResult(
        conversation=ConversationResponse.model_validate(result["conversation"]),
        sent=result["sent"],
        mode=result["mode"],
        confidence=result["confidence"],
        dispatched_payload=result["dispatched_payload"],
        message=ConversationMessage.model_validate(result["message"]) if result["message"] else None,
    )
    return Envelope.success(response)
