from __future__ import annotations

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from ..db.models import AIInterviewSession, Candidate, CandidateEmailDelivery, CandidateJobEvaluation, Job
from ..repositories.job_candidates import JobCandidateRepository
from ..repositories.workspace_scope import get_workspace_id
from ..schemas.analytics import (
    DashboardAnalyticsResult,
    EfficiencyMetric,
    FunnelStep,
    HiringCenterEvaluationItem,
    HiringCenterOverviewResult,
)


class AnalyticsService:
    _SCREENED_STAGE_ALIASES = {"screen_pass", "screened"}
    _INTERVIEW_STAGE_ALIASES = {"interview", "interviewing", "interview_scheduled", "interviewed"}
    _OFFER_STAGE_ALIASES = {"offered", "offer", "hired"}
    _DELIVERY_SENT_STATUSES = {"sent", "delivered", "opened", "clicked"}

    def __init__(self, session: Session):
        self._session = session
        self._jc_repo = JobCandidateRepository(session)

    def get_dashboard_summary(self) -> DashboardAnalyticsResult:
        counts = self._jc_repo.count_by_stage()
        total = int(self._jc_repo.get_total_synced_count() or 0)
        screened_count = self._sum_stage_counts(counts, self._SCREENED_STAGE_ALIASES)
        interviewing_count = self._sum_stage_counts(counts, self._INTERVIEW_STAGE_ALIASES)
        offered_count = self._sum_stage_counts(counts, self._OFFER_STAGE_ALIASES)

        funnel_values = [
            ("已获取人才", total, None),
            ("初筛通过", screened_count, total),
            ("面试中", interviewing_count, screened_count),
            ("拟录用", offered_count, interviewing_count),
        ]
        max_value = max((value for _, value, _ in funnel_values), default=0)
        funnel = [
            FunnelStep(
                label=label,
                value=value,
                height=self._to_height(value=value, max_value=max_value),
                opacity=max(0.35, 1 - index * 0.18),
                growth=self._to_percent(value, base),
                conversion=self._to_percent_text(value, base),
            )
            for index, (label, value, base) in enumerate(funnel_values)
        ]

        return DashboardAnalyticsResult(
            funnel=funnel,
            efficiency=self._build_efficiency_metrics(total_candidates=total),
            total_synced=total,
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

    def _build_efficiency_metrics(self, *, total_candidates: int) -> list[EfficiencyMetric]:
        sent_count = self._count_invitation_deliveries(self._DELIVERY_SENT_STATUSES)
        opened_count = self._count_invitation_deliveries({"opened", "clicked"})
        sent_progress = self._to_percent(sent_count, total_candidates)
        open_rate = self._to_percent(opened_count, sent_count)
        interview_total, interview_completed = self._count_interview_sessions()
        interview_completion_rate = self._to_percent(interview_completed, interview_total)
        saved_hours = self._estimate_saved_hours(
            total_candidates=total_candidates,
            sent_count=sent_count,
            interview_completed=interview_completed,
        )

        return [
            EfficiencyMetric(
                label="AI累计省时",
                value=str(saved_hours),
                unit="小时",
                progress=min(100, saved_hours),
            ),
            EfficiencyMetric(
                label="已发送面试邀约",
                value=str(sent_count),
                unit="封",
                progress=sent_progress,
            ),
            EfficiencyMetric(
                label="邀约打开率",
                value=str(open_rate),
                unit="%",
                progress=open_rate,
            ),
            EfficiencyMetric(
                label="AI 面试完成率",
                value=str(interview_completion_rate),
                unit="%",
                progress=interview_completion_rate,
            ),
        ]

    def _count_invitation_deliveries(self, statuses: set[str]) -> int:
        stmt = (
            select(func.count(CandidateEmailDelivery.id))
            .where(
                CandidateEmailDelivery.scene == "interview_invitation",
                CandidateEmailDelivery.status.in_(tuple(statuses)),
            )
        )
        workspace_id = get_workspace_id(self._session)
        if workspace_id:
            stmt = stmt.join(Job, Job.id == CandidateEmailDelivery.job_id).where(
                or_(
                    CandidateEmailDelivery.workspace_id == workspace_id,
                    CandidateEmailDelivery.workspace_id.is_(None) & (Job.workspace_id == workspace_id),
                )
            )
        return int(self._session.execute(stmt).scalar() or 0)

    def _count_interview_sessions(self) -> tuple[int, int]:
        total_stmt = select(func.count(AIInterviewSession.id))
        completed_stmt = select(func.count(AIInterviewSession.id)).where(AIInterviewSession.status == "completed")
        workspace_id = get_workspace_id(self._session)
        if workspace_id:
            total_stmt = total_stmt.where(AIInterviewSession.workspace_id == workspace_id)
            completed_stmt = completed_stmt.where(AIInterviewSession.workspace_id == workspace_id)
        total = int(self._session.execute(total_stmt).scalar() or 0)
        completed = int(self._session.execute(completed_stmt).scalar() or 0)
        return total, completed

    def _list_latest_evaluation_rows(self, *, max_scan: int) -> list[tuple[CandidateJobEvaluation, Candidate, Job]]:
        capped_limit = max(100, min(int(max_scan), 10000))
        workspace_id = get_workspace_id(self._session)
        latest_ts_subq = (
            select(
                CandidateJobEvaluation.candidate_id.label("candidate_id"),
                CandidateJobEvaluation.job_id.label("job_id"),
                func.max(CandidateJobEvaluation.updated_at).label("latest_updated_at"),
            )
            .group_by(CandidateJobEvaluation.candidate_id, CandidateJobEvaluation.job_id)
            .subquery()
        )
        if workspace_id:
            latest_ts_subq = (
                select(
                    CandidateJobEvaluation.candidate_id.label("candidate_id"),
                    CandidateJobEvaluation.job_id.label("job_id"),
                    func.max(CandidateJobEvaluation.updated_at).label("latest_updated_at"),
                )
                .where(CandidateJobEvaluation.workspace_id == workspace_id)
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
        if workspace_id:
            stmt = stmt.where(
                CandidateJobEvaluation.workspace_id == workspace_id,
                Candidate.workspace_id == workspace_id,
                Job.workspace_id == workspace_id,
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

    def _sum_stage_counts(self, counts: dict[str, int], aliases: set[str]) -> int:
        return sum(int(count or 0) for stage, count in counts.items() if str(stage or "").strip().lower() in aliases)

    def _to_percent(self, value: int, base: int | None) -> int:
        if not base:
            return 0
        return int(round((max(0, value) / base) * 100))

    def _to_percent_text(self, value: int, base: int | None) -> str | None:
        if not base:
            return None
        return f"{self._to_percent(value, base)}%"

    def _to_height(self, *, value: int, max_value: int) -> str:
        if max_value <= 0:
            return "24%"
        pct = max(24, round((max(0, value) / max_value) * 100))
        return f"{pct}%"

    def _estimate_saved_hours(self, *, total_candidates: int, sent_count: int, interview_completed: int) -> int:
        # Derived from actual automation volume: resume processing + invitation sending + completed AI interviews.
        saved_minutes = (total_candidates * 3) + (sent_count * 5) + (interview_completed * 45)
        return int(round(saved_minutes / 60))


def get_analytics_service(session: Session) -> AnalyticsService:
    return AnalyticsService(session)
