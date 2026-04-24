"""会话 API 数据模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConversationMessage(BaseModel):
    """会话消息结构。"""

    external_message_id: str | None = None
    direction: str
    sender: str
    content: str
    sent_at: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class ConversationResponse(BaseModel):
    """会话标准响应体。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    candidate_id: str
    channel: str
    external_conversation_id: str
    status: str
    last_message_at: datetime | None
    context_payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ConversationGreetRequest(BaseModel):
    """打招呼请求体。"""

    candidate_id: str
    template_id: str = "default"
    variables: dict[str, Any] = Field(default_factory=dict)
    channel: str | None = None


class ConversationGreetResult(BaseModel):
    """打招呼结果。"""

    conversation: ConversationResponse
    dispatched: bool
    dispatch_payload: dict[str, Any] = Field(default_factory=dict)


class ConversationSyncRequest(BaseModel):
    """会话同步请求体。"""

    max_pages: int = Field(default=1, ge=1, le=20)


class ConversationSyncResult(BaseModel):
    """会话同步结果。"""

    conversation: ConversationResponse
    pulled_count: int
    next_cursor: str | None
    has_more: bool
    messages: list[ConversationMessage] = Field(default_factory=list)


class ConversationReplyRequest(BaseModel):
    """会话回复请求体。"""

    conversation_id: str
    message: str | None = None
    auto: bool = False


class ConversationReplyResult(BaseModel):
    """会话回复结果。"""

    conversation: ConversationResponse
    sent: bool
    mode: str
    confidence: float | None = None
    action: str | None = None
    decision_reason: str | None = None
    policy_flags: list[str] = Field(default_factory=list)
    dispatched_payload: dict[str, Any] = Field(default_factory=dict)
    message: ConversationMessage | None = None
