from __future__ import annotations
from pydantic import BaseModel, Field

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


class DashboardDailyDelta(BaseModel):
    open_jobs: int = 0
    total_candidates: int = 0
    pending_interviews: int = 0
    pending_invitations: int = 0
    monthly_hires: int = 0


class DashboardAnalyticsResult(BaseModel):
    funnel: list[FunnelStep]
    efficiency: list[EfficiencyMetric]
    total_synced: int
    interview_task_count_today: int = 0
    daily_deltas: DashboardDailyDelta = Field(default_factory=DashboardDailyDelta)


class HiringCenterEvaluationItem(BaseModel):
    candidate_id: str
    candidate_name: str
    avatar_url: str | None = None
    candidate_stage: str
    candidate_expected_salary: str | None = None
    candidate_score_explanation: str | None = None
    job_id: str
    job_title: str
    job_salary_range: str | None = None
    evaluation_status: str
    resume_score: float | None = None
    interview_score: float | None = None
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


class HiringDecisionDimensionItem(BaseModel):
    key: str
    label: str
    score: float
    max_score: float = 100.0


class HiringDecisionCandidateProfile(BaseModel):
    candidate_id: str
    candidate_name: str
    avatar_url: str | None = None
    phone: str | None = None
    email: str | None = None
    city: str | None = None
    degree: str | None = None
    work_experience: str | None = None
    current_role: str | None = None
    current_stage: str
    expected_salary: str | None = None
    applied_at: str | None = None
    updated_at: str | None = None
    job_id: str
    job_title: str
    department: str | None = None
    job_city: str | None = None
    job_salary_range: str | None = None


class HiringDecisionOverview(BaseModel):
    resume_score: float
    interview_score: float
    composite_score: float
    grade: str
    recommendation: str
    recommended_salary: str | None = None
    updated_at: str | None = None


class HiringDecisionAssessmentPanel(BaseModel):
    score: float
    summary: str | None = None
    dimensions: list[HiringDecisionDimensionItem] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    risk_tags: list[str] = Field(default_factory=list)


class HiringDecisionTimelineItem(BaseModel):
    step: str
    time: str | None = None
    status: str | None = None


class HiringDecisionInterviewerReviewItem(BaseModel):
    reviewer: str
    stage: str | None = None
    score: float | None = None
    time: str | None = None
    comment: str | None = None


class HiringDecisionQAItem(BaseModel):
    question: str
    answer: str | None = None
    turn_no: int | None = None
    occurred_at: str | None = None


class HiringDecisionOperationLogItem(BaseModel):
    type: str
    title: str
    status: str | None = None
    time: str | None = None
    detail: str | None = None


class HiringDecisionDetailResult(BaseModel):
    profile: HiringDecisionCandidateProfile
    overview: HiringDecisionOverview
    resume_assessment: HiringDecisionAssessmentPanel
    interview_assessment: HiringDecisionAssessmentPanel
    composite_assessment: HiringDecisionAssessmentPanel
    timeline: list[HiringDecisionTimelineItem] = Field(default_factory=list)
    interviewer_reviews: list[HiringDecisionInterviewerReviewItem] = Field(default_factory=list)
    qa_items: list[HiringDecisionQAItem] = Field(default_factory=list)
    operation_logs: list[HiringDecisionOperationLogItem] = Field(default_factory=list)
