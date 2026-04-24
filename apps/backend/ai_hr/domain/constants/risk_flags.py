from __future__ import annotations

from enum import StrEnum


class GuardrailMaskToken(StrEnum):
    PHONE = "[PHONE]"
    EMAIL = "[EMAIL]"


class RiskTag(StrEnum):
    LLM_UNAVAILABLE = "llm_unavailable"
    INSUFFICIENT_RESPONSE = "insufficient_response"
    LOW_CONFIDENCE_ANSWERS = "low_confidence_answers"
    SENSITIVE_CONTENT = "sensitive_content"


class ValidationFlag(StrEnum):
    REPLY_EMPTY = "reply_empty"


class HandoffReason(StrEnum):
    LOW_CONFIDENCE_STREAK = "low_confidence_streak"


class BlockReason(StrEnum):
    SENSITIVE_CONTENT = "sensitive_content"


SENSITIVE_FLAG_PREFIX = "sensitive:"


def build_sensitive_flag(keyword: str) -> str:
    return f"{SENSITIVE_FLAG_PREFIX}{keyword}"
