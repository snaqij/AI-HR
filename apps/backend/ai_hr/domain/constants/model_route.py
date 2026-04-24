from __future__ import annotations

from enum import StrEnum


class ModelRoutePolicy(StrEnum):
    QUALITY_FIRST = "quality_first"
    COST_FIRST = "cost_first"
    BALANCED = "balanced"


class ModelRouteResult(StrEnum):
    QUALITY_MAX = "quality_max"
    COST_OPTIMIZED = "cost_optimized"
    BALANCED = "balanced"
