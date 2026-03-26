"""会话服务编排。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from ..connectors.base import ConnectorCredentials
from ..connectors.registry import registry
from ..core.config import get_settings
from ..core.exceptions import ConnectorOperationError
from ..repositories.candidates import CandidateRepository
from ..repositories.conversations import ConversationRepository
from ..repositories.events import EventRepository
from ..repositories.ai_runtime import AIRuntimeRepository
from ..schemas.conversations import (
    ConversationGreetRequest,
    ConversationReplyRequest,
    ConversationSyncRequest,
)
from .ai_reply_llm import AIReplyLLMService


class ConversationService:
    """负责打招呼、消息同步、自动回复的会话业务编排。"""

    def __init__(
        self,
        conversation_repository: ConversationRepository,
        candidate_repository: CandidateRepository,
        event_repository: EventRepository,
        ai_reply_service: AIReplyLLMService,
        runtime_repository: AIRuntimeRepository,
    ):
        """注入仓储并加载运行时配置。"""
        self._conversation_repository = conversation_repository
        self._candidate_repository = candidate_repository
        self._event_repository = event_repository
        self._settings = get_settings()
        self._ai_reply_service = ai_reply_service
        self._runtime_repository = runtime_repository

    def greet(self, payload: ConversationGreetRequest) -> dict[str, Any]:
        """发送首轮打招呼消息并初始化会话状态。"""
        candidate = self._candidate_repository.get(payload.candidate_id)
        channel = payload.channel or candidate.source_channel
        connector = self._build_connector(channel)

        dispatch = connector.send_greeting(
            candidate_external_id=candidate.external_candidate_id,
            template_id=payload.template_id,
            variables=payload.variables,
        )
        external_conversation_id = self._extract_external_conversation_id(dispatch, candidate.external_candidate_id)
        conversation = self._conversation_repository.create_or_get(
            candidate_id=candidate.id,
            channel=channel,
            external_conversation_id=external_conversation_id,
            status="open",
            context_payload={"messages": [], "sync_cursor": None, "has_more": False, "message_count": 0},
        )

        now = datetime.now(UTC).replace(tzinfo=None).isoformat()
        message = {
            "external_message_id": dispatch.get("message_id"),
            "direction": "outbound",
            "sender": "hr",
            "content": dispatch.get("content") or self._render_greeting_content(payload.template_id, payload.variables),
            "sent_at": now,
            "meta": {"type": "greeting", "template_id": payload.template_id},
        }
        conversation = self._conversation_repository.append_messages(
            conversation.id,
            messages=[message],
            status="open",
        )
        self._candidate_repository.update_stage(candidate.id, "contacted")
        self._event_repository.create(
            event_type="conversation.greet.sent",
            entity_type="conversation",
            entity_id=conversation.id,
            channel=channel,
            payload={"candidate_id": candidate.id, "dispatch": dispatch},
        )

        return {"conversation": conversation, "dispatched": True, "dispatch_payload": dispatch}

    def sync_messages(self, conversation_id: str, payload: ConversationSyncRequest) -> dict[str, Any]:
        """按游标拉取新消息并追加到本地会话上下文。"""
        conversation = self._conversation_repository.get(conversation_id)
        connector = self._build_connector(conversation.channel)
        cursor = self._read_sync_cursor(conversation.context_payload)
        pulled_count = 0
        has_more = False
        newest_messages: list[dict[str, Any]] = []

        for _ in range(payload.max_pages):
            result = connector.fetch_messages(conversation.external_conversation_id, cursor=cursor)
            page_messages = result.get("messages", [])
            if page_messages:
                newest_messages.extend(page_messages)
                pulled_count += len(page_messages)
            cursor = result.get("next_cursor")
            has_more = bool(result.get("has_more", False))
            if not has_more or cursor is None:
                break

        conversation = self._conversation_repository.append_messages(
            conversation.id,
            messages=newest_messages,
            next_cursor=cursor,
            has_more=has_more,
            status="open",
        )
        self._event_repository.create(
            event_type="conversation.sync.completed",
            entity_type="conversation",
            entity_id=conversation.id,
            channel=conversation.channel,
            payload={"pulled_count": pulled_count, "next_cursor": cursor, "has_more": has_more},
        )
        return {
            "conversation": conversation,
            "pulled_count": pulled_count,
            "next_cursor": cursor,
            "has_more": has_more,
            "messages": newest_messages,
        }

    def reply(self, payload: ConversationReplyRequest) -> dict[str, Any]:
        """执行手动/自动回复，低置信度时转人工处理。"""
        conversation = self._conversation_repository.get(payload.conversation_id)
        connector = self._build_connector(conversation.channel)

        generated_message = payload.message
        confidence: float | None = None
        mode = "manual"
        if payload.auto:
            mode = "auto"
            if self._is_reply_llm_enabled():
                latest_message = self._extract_latest_inbound_text(conversation.context_payload)
                generated_message, confidence, policy_flags, action = self._ai_reply_service.generate_reply(
                    conversation_id=conversation.id,
                    latest_message=latest_message or "你好",
                )
                if action in {"handoff", "blocked"}:
                    conversation = self._conversation_repository.update_status(conversation.id, "needs_human")
                    self._event_repository.create(
                        event_type="conversation.reply.handoff",
                        entity_type="conversation",
                        entity_id=conversation.id,
                        channel=conversation.channel,
                        status="success",
                        payload={"confidence": confidence, "reason": action, "policy_flags": policy_flags},
                    )
                    return {
                        "conversation": conversation,
                        "sent": False,
                        "mode": mode,
                        "confidence": confidence,
                        "dispatched_payload": {},
                        "message": None,
                    }
            else:
                generated_message, confidence = self._generate_auto_reply(conversation.context_payload)
            if confidence is not None and confidence < 0.6:
                conversation = self._conversation_repository.update_status(conversation.id, "needs_human")
                self._event_repository.create(
                    event_type="conversation.reply.handoff",
                    entity_type="conversation",
                    entity_id=conversation.id,
                    channel=conversation.channel,
                    status="success",
                    payload={"confidence": confidence, "reason": "low_confidence"},
                )
                return {
                    "conversation": conversation,
                    "sent": False,
                    "mode": mode,
                    "confidence": confidence,
                    "dispatched_payload": {},
                    "message": None,
                }

        if not generated_message:
            generated_message = "您好，已收到您的信息，我们会尽快处理并回复。"

        dispatch = connector.send_message(conversation.external_conversation_id, generated_message)
        message = {
            "external_message_id": dispatch.get("message_id"),
            "direction": "outbound",
            "sender": "hr",
            "content": generated_message,
            "sent_at": dispatch.get("sent_at") or datetime.now(UTC).replace(tzinfo=None).isoformat(),
            "meta": {"type": "reply", "mode": mode, "confidence": confidence},
        }
        conversation = self._conversation_repository.append_messages(
            conversation.id,
            messages=[message],
            status="open",
        )
        self._event_repository.create(
            event_type="conversation.reply.sent",
            entity_type="conversation",
            entity_id=conversation.id,
            channel=conversation.channel,
            payload={"mode": mode, "confidence": confidence, "dispatch": dispatch},
        )
        return {
            "conversation": conversation,
            "sent": True,
            "mode": mode,
            "confidence": confidence,
            "dispatched_payload": dispatch,
            "message": message,
        }

    def _build_connector(self, channel: str):
        """根据渠道构建连接器实例。"""
        if channel == "boss":
            credentials = ConnectorCredentials(
                account=self._settings.boss_account,
                secret=self._settings.boss_secret,
                mode=self._settings.boss_mode,
                base_url=self._settings.boss_base_url,
                publish_path=self._settings.boss_publish_path,
                status_path=self._settings.boss_status_path,
                applicants_path=self._settings.boss_applicants_path,
                greet_path=self._settings.boss_greet_path,
                fetch_messages_path=self._settings.boss_fetch_messages_path,
                send_message_path=self._settings.boss_send_message_path,
                interview_schedule_path=self._settings.boss_interview_schedule_path,
                interview_status_path=self._settings.boss_interview_status_path,
                cookie_header=self._settings.boss_cookie_header,
                credential_file=self._settings.boss_credential_file,
                timeout_seconds=self._settings.boss_timeout_seconds,
            )
            return registry.create(channel, credentials)
        raise ConnectorOperationError(f"Connector '{channel}' is not configured")

    def _extract_external_conversation_id(self, payload: dict[str, Any], fallback_key: str) -> str:
        """从渠道返回结果中提取会话 ID。"""
        for key in ("external_conversation_id", "externalConversationId", "conversationId", "id"):
            value = payload.get(key)
            if value:
                return str(value)
        return f"conv-{fallback_key}"

    def _render_greeting_content(self, template_id: str, variables: dict[str, Any]) -> str:
        """当渠道未返回内容时，渲染兜底打招呼文案。"""
        name = variables.get("name") or "你好"
        role = variables.get("job_title") or "这个岗位"
        if template_id == "short":
            return f"{name}，我们有一个{role}机会，方便了解下吗？"
        return f"{name}，你好！我们在招聘{role}，看了你的背景很匹配，方便沟通下吗？"

    def _read_sync_cursor(self, context_payload: dict[str, Any]) -> str | None:
        """读取会话上下文中保存的同步游标。"""
        if not isinstance(context_payload, dict):
            return None
        value = context_payload.get("sync_cursor")
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    def _extract_latest_inbound_text(self, context_payload: dict[str, Any]) -> str | None:
        """提取最近一条入站消息文本。"""
        messages = context_payload.get("messages", []) if isinstance(context_payload, dict) else []
        for item in reversed(messages):
            if not isinstance(item, dict):
                continue
            if item.get("direction") == "inbound":
                content = str(item.get("content") or "").strip()
                if content:
                    return content
        return None

    def _generate_auto_reply(self, context_payload: dict[str, Any]) -> tuple[str, float]:
        """基于最近入站消息生成启发式自动回复与置信度。"""
        messages = context_payload.get("messages", []) if isinstance(context_payload, dict) else []
        latest_inbound = None
        for item in reversed(messages):
            if not isinstance(item, dict):
                continue
            if item.get("direction") == "inbound":
                latest_inbound = item
                break

        if not latest_inbound:
            return "您好，感谢关注，我们会尽快安排后续沟通。", 0.7

        content = str(latest_inbound.get("content") or "").lower()
        if any(keyword in content for keyword in ("薪资", "salary", "多少钱", "package")):
            return "薪资范围会结合岗位级别和面试表现综合评估，这块可在后续沟通时详细说明。", 0.55
        if any(keyword in content for keyword in ("地点", "city", "remote", "远程")):
            return "工作地点和远程政策可根据团队安排确认，我这边先帮你记录并推进下一步。", 0.86
        if any(keyword in content for keyword in ("你好", "hello", "hi")):
            return "你好，感谢回复。我们会尽快安排下一步沟通，并同步具体时间。", 0.95
        return "感谢你的反馈，我已记录你的信息，稍后会由招聘同学进一步与您沟通。", 0.75

    def _is_reply_llm_enabled(self) -> bool:
        """判定会话自动回复链路是否启用 LLM。"""
        return self._runtime_repository.is_feature_enabled(
            feature_key="ai_reply_llm",
            default_enabled=self._settings.ai_reply_llm_enabled,
        )


def get_conversation_service(session: Session) -> ConversationService:
    """返回绑定当前数据库会话的 ConversationService。"""
    return ConversationService(
        conversation_repository=ConversationRepository(session),
        candidate_repository=CandidateRepository(session),
        event_repository=EventRepository(session),
        ai_reply_service=AIReplyLLMService(session),
        runtime_repository=AIRuntimeRepository(session),
    )
