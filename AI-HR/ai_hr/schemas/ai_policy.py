"""AI 策略决策数据模型。"""

from __future__ import annotations

from pydantic import BaseModel


class PolicyDecisionResult(BaseModel):
    """策略决策结果。"""

    action: str
    policy_flags: list[str]
    reason: str

