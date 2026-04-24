"""会话自动回复 LLM 服务。"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..repositories.ai_observability import AIObservabilityRepository
from ..repositories.ai_runtime import AIRuntimeRepository
from ..schemas.ai_reply import AIIntentClassifyResult, AIReplyAlertStatsResult, AIReplyGenerateResult
from .llm.client import InvokeContext, LLMClient
from .llm.guardrails import GuardrailService
from .llm.prompts import get_prompt_template
from .llm.router import ModelRouter
from .policy.decision import PolicyDecisionService


class AIReplyLLMService:
    """提供意图分类与回复生成能力。"""

    _SENSITIVE_KEYWORDS = ("身份证", "银行卡", "种族", "宗教", "违法")

    def __init__(self, session: Session):
        """初始化依赖组件。"""
        runtime_repository = AIRuntimeRepository(session)
        observability_repository = AIObservabilityRepository(session)
        self._settings = get_settings()
        self._observability_repository = observability_repository
        self._llm_client = LLMClient(
            router=ModelRouter(runtime_repository),
            guardrail_service=GuardrailService(),
            observability_repository=observability_repository,
        )
        self._policy_service = PolicyDecisionService()

    def classify_intent(self, *, conversation_id: str, message: str) -> AIIntentClassifyResult:
        """对会话消息执行意图分类。"""
        template = get_prompt_template("intent_classify", "v1")
        prompt = "\n".join([template.system_prompt, template.render(message=message)])
        invoke_result = self._llm_client.invoke_json(
            InvokeContext(
                task_key="intent_classify",
                trace_id=str(uuid.uuid4()),
                prompt=prompt,
                entity_type="conversation",
                entity_id=conversation_id,
            )
        )

        payload = invoke_result.content if not invoke_result.fallback_used else {"intent": "general", "confidence": 0.55, "policy_flags": ["llm_failed"]}
        intent = str(payload.get("intent") or "general")
        confidence = float(payload.get("confidence") or 0.55)
        policy_flags = [str(item) for item in payload.get("policy_flags", [])]
        explanation = self._build_intent_explanation(message=message, intent=intent, policy_flags=policy_flags)
        return AIIntentClassifyResult(
            conversation_id=conversation_id,
            intent=intent,
            confidence=confidence,
            policy_flags=policy_flags,
            explanation=explanation,
            provider=invoke_result.provider,
            model_name=invoke_result.model_name,
            prompt_version=invoke_result.prompt_version,
        )

    def generate_reply_result(
        self,
        *,
        conversation_id: str,
        message: str,
        intent_hint: str | None = None,
    ) -> AIReplyGenerateResult:
        """生成自动回复并返回可解释结构。"""
        classify = self.classify_intent(conversation_id=conversation_id, message=message)
        intent = intent_hint or classify.intent

        template = get_prompt_template("reply_generate", "v1")
        prompt = "\n".join([template.system_prompt, template.render(message=message, intent=intent)])
        invoke_result = self._llm_client.invoke_json(
            InvokeContext(
                task_key="reply_generate",
                trace_id=str(uuid.uuid4()),
                prompt=prompt,
                entity_type="conversation",
                entity_id=conversation_id,
            )
        )
        payload = invoke_result.content if not invoke_result.fallback_used else {"reply_text": "", "confidence": 0.45, "policy_flags": ["llm_failed"]}

        reply_text = str(payload.get("reply_text") or "")
        reply_confidence = float(payload.get("confidence") or 0.45)
        policy_flags = classify.policy_flags + [str(item) for item in payload.get("policy_flags", [])]
        policy_flags.extend(self._detect_sensitive_flags(message))
        policy_flags = list(dict.fromkeys(policy_flags))

        final_confidence = round(min(classify.confidence, reply_confidence), 2)
        decision = self._policy_service.decide_reply_action(confidence=final_confidence, policy_flags=policy_flags)

        explanation = self._build_reply_explanation(
            message=message,
            intent=intent,
            action=decision.action,
            decision_reason=decision.reason,
            policy_flags=decision.policy_flags,
        )
        self._observability_repository.create_decision_log(
            trace_id=str(uuid.uuid4()),
            module_key="reply_policy",
            entity_type="conversation",
            entity_id=conversation_id,
            action=decision.action,
            confidence=final_confidence,
            policy_flags=decision.policy_flags,
            input_summary=message[:200],
            output_summary=reply_text[:500],
            provider=invoke_result.provider,
            model_name=invoke_result.model_name,
            prompt_version=invoke_result.prompt_version,
            extra_payload={"reason": decision.reason, "intent": intent},
        )
        return AIReplyGenerateResult(
            conversation_id=conversation_id,
            intent=intent,
            reply_text=reply_text,
            confidence=final_confidence,
            action=decision.action,
            decision_reason=decision.reason,
            policy_flags=decision.policy_flags,
            explanation=explanation,
            provider=invoke_result.provider,
            model_name=invoke_result.model_name,
            prompt_version=invoke_result.prompt_version,
        )

    def generate_reply(self, *, conversation_id: str, latest_message: str) -> tuple[str, float, list[str], str, str]:
        """兼容旧流程：返回回复文本、置信度、策略标记、动作、动作原因。"""
        result = self.generate_reply_result(conversation_id=conversation_id, message=latest_message)
        return result.reply_text, result.confidence, result.policy_flags, result.action, result.decision_reason

    def get_reply_alert_stats(self) -> AIReplyAlertStatsResult:
        """读取自动回复策略告警统计。"""
        stats = self._observability_repository.get_reply_alert_stats(
            window_minutes=self._settings.ai_reply_alert_window_minutes,
            handoff_alert_threshold=self._settings.ai_reply_handoff_alert_threshold,
            blocked_alert_threshold=self._settings.ai_reply_blocked_alert_threshold,
            min_samples=self._settings.ai_reply_alert_min_samples,
        )
        return AIReplyAlertStatsResult.model_validate(stats)

    def _detect_sensitive_flags(self, message: str) -> list[str]:
        """根据输入内容补充敏感标记。"""
        flags: list[str] = []
        text = message or ""
        for keyword in self._SENSITIVE_KEYWORDS:
            if keyword in text:
                flags.append(f"sensitive:{keyword}")
        return flags

    def _build_intent_explanation(self, *, message: str, intent: str, policy_flags: list[str]) -> str:
        """生成意图分类可解释输出。"""
        signals = []
        lowered = message.lower()
        if any(keyword in lowered for keyword in ("salary", "package", "薪资", "多少钱")):
            signals.append("薪资关键词命中")
        if any(keyword in lowered for keyword in ("hello", "hi", "你好")):
            signals.append("问候关键词命中")
        if not signals:
            signals.append("通用语义匹配")
        flag_hint = f"；策略标记={','.join(policy_flags)}" if policy_flags else ""
        return f"意图={intent}；依据={','.join(signals)}{flag_hint}"

    def _build_reply_explanation(
        self,
        *,
        message: str,
        intent: str,
        action: str,
        decision_reason: str,
        policy_flags: list[str],
    ) -> str:
        """生成回复结果可解释输出。"""
        msg_len = len(message.strip())
        flag_hint = ",".join(policy_flags) if policy_flags else "none"
        return f"基于意图={intent}生成回复；消息长度={msg_len}；动作={action}；原因={decision_reason}；策略标记={flag_hint}"


def get_ai_reply_llm_service(session: Session) -> AIReplyLLMService:
    """返回绑定当前数据库会话的 AIReplyLLMService。"""
    return AIReplyLLMService(session)
