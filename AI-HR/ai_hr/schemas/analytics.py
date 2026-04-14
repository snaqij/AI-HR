from __future__ import annotations
from pydantic import BaseModel

class FunnelStep(BaseModel):
    label: str
    value: int
    growth: int = 0
    height: str = "60%"
    opacity: float = 1.0
    conversion: str | None = None

class EfficiencyMetric(BaseModel):
    label: str
    value: str
    unit: str
    progress: int

class DashboardAnalyticsResult(BaseModel):
    funnel: list[FunnelStep]
    efficiency: list[EfficiencyMetric]
    total_synced: int
