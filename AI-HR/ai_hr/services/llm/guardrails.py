"""输入输出合规守卫。"""

from __future__ import annotations

import re
from typing import Any

from ai_hr.domain.constants import GuardrailMaskToken, PromptTaskKey, ValidationFlag, build_sensitive_flag


class GuardrailService:
    """提供基础脱敏与输出规则校验。"""

    _SENSITIVE_KEYWORDS = ("身份证", "银行卡", "违法", "种族", "宗教歧视")

    def sanitize_input(self, text: str) -> str:
        """对输入文本做基础脱敏。"""
        sanitized = text or ""
        sanitized = re.sub(r"\b1\d{10}\b", GuardrailMaskToken.PHONE, sanitized)
        sanitized = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", GuardrailMaskToken.EMAIL, sanitized)
        return sanitized

    def validate_output(self, *, task_key: str, payload: dict[str, Any]) -> tuple[bool, list[str]]:
        """校验输出是否命中合规风险。"""
        flags: list[str] = []
        flattened = str(payload)
        for keyword in self._SENSITIVE_KEYWORDS:
            if keyword in flattened:
                flags.append(build_sensitive_flag(keyword))
        if task_key == PromptTaskKey.REPLY_GENERATE and not payload.get("reply_text"):
            flags.append(ValidationFlag.REPLY_EMPTY)
        return len(flags) == 0, flags
