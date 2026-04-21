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


class HiringCenterEvaluationItem(BaseModel):
    candidate_id: str
    candidate_name: str
    candidate_stage: str
    candidate_expected_salary: str | None = None
    candidate_score_explanation: str | None = None
    job_id: str
    job_title: str
    job_salary_range: str | None = None
    evaluation_status: str
    final_score: float
    recommendation: str
    summary: str | None = None
    highlights: list[str] = []
    invited_flag: bool
    updated_at: str
    created_at: str


class HiringCenterOverviewResult(BaseModel):
    total: int
    review_count: int
    invited_count: int
    recommended_count: int
    conversion_rate: float
    top_items: list[HiringCenterEvaluationItem]
    queue_items: list[HiringCenterEvaluationItem]
