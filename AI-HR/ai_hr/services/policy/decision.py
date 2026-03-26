"""策略决策服务。"""

from __future__ import annotations

from ...core.config import get_settings
from ...schemas.ai_policy import PolicyDecisionResult
from .thresholds import PolicyThresholds


class PolicyDecisionService:
    """根据置信度和风险信号决定自动化动作。"""

    def __init__(self, thresholds: PolicyThresholds | None = None):
        """注入阈值配置，默认从配置文件读取。"""
        if thresholds is not None:
            self._thresholds = thresholds
            return

        settings = get_settings()
        self._thresholds = PolicyThresholds(
            auto_reply_min_confidence=settings.ai_reply_auto_min_confidence,
            auto_score_min_confidence=0.60,
            sensitive_block_enabled=settings.ai_reply_sensitive_block_enabled,
        )

    def decide_reply_action(self, *, confidence: float, policy_flags: list[str]) -> PolicyDecisionResult:
        """决定回复动作：自动发送、转人工或拦截。"""
        flags = list(policy_flags or [])
        if self._thresholds.sensitive_block_enabled and any(flag.startswith("sensitive:") for flag in flags):
            return PolicyDecisionResult(action="blocked", policy_flags=flags, reason="sensitive_content")
        if confidence < self._thresholds.auto_reply_min_confidence:
            flags.append("low_confidence")
            return PolicyDecisionResult(action="handoff", policy_flags=flags, reason="low_confidence")
        return PolicyDecisionResult(action="auto_send", policy_flags=flags, reason="confidence_passed")

    def decide_score_action(self, *, confidence: float, risk_tags: list[str]) -> PolicyDecisionResult:
        """决定评分结果是否可直接用于自动化。"""
        tags = list(risk_tags or [])
        if confidence < self._thresholds.auto_score_min_confidence:
            tags.append("low_confidence")
            return PolicyDecisionResult(action="manual_review", policy_flags=tags, reason="low_confidence")
        if "skills_missing" in tags:
            return PolicyDecisionResult(action="manual_review", policy_flags=tags, reason="skills_missing")
        return PolicyDecisionResult(action="accepted", policy_flags=tags, reason="policy_passed")
