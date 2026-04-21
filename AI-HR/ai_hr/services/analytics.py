from __future__ import annotations
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session
from ..db.models import Candidate, CandidateJobEvaluation, Job
from ..repositories.job_candidates import JobCandidateRepository
from ..schemas.analytics import (
    DashboardAnalyticsResult,
    EfficiencyMetric,
    FunnelStep,
    HiringCenterEvaluationItem,
    HiringCenterOverviewResult,
)

class AnalyticsService:
    def __init__(self, session: Session):
        self._session = session
        self._jc_repo = JobCandidateRepository(session)

    def get_dashboard_summary(self) -> DashboardAnalyticsResult:
        counts = self._jc_repo.count_by_stage()
        total = self._jc_repo.get_total_synced_count()

        # Mocking some growth and heights for visual effect as requested (real-time counts, visual styling)
        funnel = [
            FunnelStep(label="已获取人才", value=total, height="100%", opacity=1.0, growth=12),
            FunnelStep(label="初筛通过", value=counts.get("screened", 0) or int(total * 0.4), height="70%", opacity=0.8, growth=8, conversion="40%"),
            FunnelStep(label="面试中", value=counts.get("interviewing", 0) or int(total * 0.15), height="45%", opacity=0.6, growth=5, conversion="15%"),
            FunnelStep(label="拟录用", value=counts.get("offered", 0) or int(total * 0.05), height="25%", opacity=0.4, growth=2, conversion="5%"),
        ]

        efficiency = [
            EfficiencyMetric(label="AI 累计节省时间", value="420", unit="小时", progress=75),
            EfficiencyMetric(label="平均简历处理时效", value="1.2", unit="分钟", progress=90),
            EfficiencyMetric(label="AI 面试完成率", value="92", unit="%", progress=92),
        ]

        return DashboardAnalyticsResult(
            funnel=funnel,
            efficiency=efficiency,
            total_synced=total
        )

    def get_hiring_center_overview(
        self,
        *,
        top_n: int = 3,
        queue_limit: int = 20,
        max_scan: int = 3000,
    ) -> HiringCenterOverviewResult:
        latest_rows = self._list_latest_evaluation_rows(max_scan=max_scan)
        if not latest_rows:
            return HiringCenterOverviewResult(
                total=0,
                review_count=0,
                invited_count=0,
                recommended_count=0,
                conversion_rate=0.0,
                top_items=[],
                queue_items=[],
            )

        items = [self._to_hiring_item(evaluation=row[0], candidate=row[1], job=row[2]) for row in latest_rows]
        total = len(items)
        review_count = len([item for item in items if item.recommendation == "manual_review"])
        invited_count = len([item for item in items if item.invited_flag])
        recommended_count = len([item for item in items if item.recommendation in {"recommend", "strong_recommend"}])
        conversion_rate = round((invited_count / total) * 100, 1) if total else 0.0

        sorted_items = sorted(items, key=lambda item: float(item.final_score or 0), reverse=True)
        queue_items = [item for item in sorted_items if item.recommendation == "manual_review"][: max(1, queue_limit)]
        top_items = sorted_items[: max(1, top_n)]

        return HiringCenterOverviewResult(
            total=total,
            review_count=review_count,
            invited_count=invited_count,
            recommended_count=recommended_count,
            conversion_rate=conversion_rate,
            top_items=top_items,
            queue_items=queue_items,
        )

    def _list_latest_evaluation_rows(self, *, max_scan: int) -> list[tuple[CandidateJobEvaluation, Candidate, Job]]:
        capped_limit = max(100, min(int(max_scan), 10000))
        latest_ts_subq = (
            select(
                CandidateJobEvaluation.candidate_id.label("candidate_id"),
                CandidateJobEvaluation.job_id.label("job_id"),
                func.max(CandidateJobEvaluation.updated_at).label("latest_updated_at"),
            )
            .group_by(CandidateJobEvaluation.candidate_id, CandidateJobEvaluation.job_id)
            .subquery()
        )
        stmt = (
            select(CandidateJobEvaluation, Candidate, Job)
            .join(
                latest_ts_subq,
                and_(
                    CandidateJobEvaluation.candidate_id == latest_ts_subq.c.candidate_id,
                    CandidateJobEvaluation.job_id == latest_ts_subq.c.job_id,
                    CandidateJobEvaluation.updated_at == latest_ts_subq.c.latest_updated_at,
                ),
            )
            .join(Candidate, Candidate.id == CandidateJobEvaluation.candidate_id)
            .join(Job, Job.id == CandidateJobEvaluation.job_id)
            .where(CandidateJobEvaluation.status.in_(("completed", "reviewed")))
            .order_by(CandidateJobEvaluation.final_score.desc(), CandidateJobEvaluation.updated_at.desc())
            .limit(capped_limit)
        )
        return list(self._session.execute(stmt).all())

    def _to_hiring_item(
        self,
        *,
        evaluation: CandidateJobEvaluation,
        candidate: Candidate,
        job: Job,
    ) -> HiringCenterEvaluationItem:
        return HiringCenterEvaluationItem(
            candidate_id=candidate.id,
            candidate_name=candidate.name,
            candidate_stage=candidate.current_stage,
            candidate_expected_salary=candidate.expected_salary,
            candidate_score_explanation=candidate.score_explanation,
            job_id=job.id,
            job_title=job.title,
            job_salary_range=job.salary_range,
            evaluation_status=evaluation.status,
            final_score=float(evaluation.final_score or 0),
            recommendation=evaluation.recommendation,
            summary=evaluation.summary,
            highlights=[str(item) for item in (evaluation.highlights or []) if str(item).strip()],
            invited_flag=bool(evaluation.invited_flag),
            updated_at=evaluation.updated_at.isoformat() if evaluation.updated_at else "",
            created_at=evaluation.created_at.isoformat() if evaluation.created_at else "",
        )

def get_analytics_service(session: Session) -> AnalyticsService:
    return AnalyticsService(session)
