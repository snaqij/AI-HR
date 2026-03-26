"""策略阈值配置。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PolicyThresholds:
    """策略阈值。"""

    auto_reply_min_confidence: float = 0.65
    auto_score_min_confidence: float = 0.60
    sensitive_block_enabled: bool = True

