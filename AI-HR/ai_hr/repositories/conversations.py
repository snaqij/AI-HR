"""会话仓储实现。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.exceptions import ResourceNotFoundError
from ..db.models import Conversation


class ConversationRepository:
    """封装会话查询、写入与消息追加逻辑。"""

    def __init__(self, session: Session):
        """使用当前数据库会话初始化仓储。"""
        self._session = session

    def get(self, conversation_id: str) -> Conversation:
        """按会话 ID 获取会话，不存在则抛错。"""
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        conversation = self._session.execute(stmt).scalar_one_or_none()
        if conversation is None:
            raise ResourceNotFoundError(f"Conversation '{conversation_id}' was not found")
        return conversation

    def get_by_external(self, channel: str, external_conversation_id: str) -> Conversation | None:
        """按渠道+外部会话 ID 查询会话。"""
        stmt = select(Conversation).where(
            Conversation.channel == channel,
            Conversation.external_conversation_id == external_conversation_id,
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def create_or_get(
        self,
        *,
        candidate_id: str,
        channel: str,
        external_conversation_id: str,
        status: str = "open",
        context_payload: dict[str, Any] | None = None,
    ) -> Conversation:
        """按外部会话去重创建本地会话。"""
        existing = self.get_by_external(channel, external_conversation_id)
        if existing is not None:
            return existing

        conversation = Conversation(
            candidate_id=candidate_id,
            channel=channel,
            external_conversation_id=external_conversation_id,
            status=status,
            context_payload=context_payload or {},
        )
        self._session.add(conversation)
        self._session.commit()
        self._session.refresh(conversation)
        return conversation

    def append_messages(
        self,
        conversation_id: str,
        *,
        messages: list[dict[str, Any]],
        next_cursor: str | None = None,
        has_more: bool | None = None,
        status: str | None = None,
    ) -> Conversation:
        """去重追加消息，并更新游标、状态与最新消息时间。"""
        conversation = self.get(conversation_id)
        payload = dict(conversation.context_payload or {})
        existing_messages = list(payload.get("messages", []))
        known_ids = {
            str(item.get("external_message_id"))
            for item in existing_messages
            if isinstance(item, dict) and item.get("external_message_id") is not None
        }

        last_message_at = conversation.last_message_at
        for message in messages:
            message_id = message.get("external_message_id")
            normalized_id = str(message_id) if message_id is not None else None
            if normalized_id and normalized_id in known_ids:
                continue
            existing_messages.append(message)
            if normalized_id:
                known_ids.add(normalized_id)
            message_time = self._parse_message_time(message.get("sent_at"))
            if message_time and (last_message_at is None or message_time > last_message_at):
                last_message_at = message_time

        payload["messages"] = existing_messages
        if next_cursor is not None or "sync_cursor" in payload:
            payload["sync_cursor"] = next_cursor
        if has_more is not None:
            payload["has_more"] = has_more
        payload["message_count"] = len(existing_messages)
        payload["last_synced_at"] = datetime.now(UTC).isoformat()

        conversation.context_payload = payload
        conversation.last_message_at = last_message_at
        if status:
            conversation.status = status
        self._session.commit()
        self._session.refresh(conversation)
        return conversation

    def update_status(self, conversation_id: str, status: str) -> Conversation:
        """更新会话状态。"""
        conversation = self.get(conversation_id)
        conversation.status = status
        self._session.commit()
        self._session.refresh(conversation)
        return conversation

    def _parse_message_time(self, value: Any) -> datetime | None:
        """解析消息时间字符串。"""
        if not value:
            return None
        if isinstance(value, datetime):
            return value.replace(tzinfo=None)
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return parsed.replace(tzinfo=None)
            except ValueError:
                return None
        return None
