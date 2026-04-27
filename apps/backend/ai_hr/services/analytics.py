from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from ..db.models import (
    AIInterviewAssessment,
    AIInterviewReport,
    AIInterviewSession,
    AIInterviewTurn,
    Candidate,
    CandidateCompositeAssessment,
    CandidateEmailDelivery,
    CandidateJobEvaluation,
    CandidateJobPipeline,
    DecisionEvent,
    Job,
    JobCandidate,
)
from ..core.exceptions import ResourceNotFoundError
from ..repositories.job_candidates import JobCandidateRepository
from ..repositories.workspace_scope import get_workspace_id
from ..schemas.analytics import (
    DashboardDailyDelta,
    DashboardAnalyticsResult,
    EfficiencyMetric,
    FunnelStep,
    HiringCenterEvaluationItem,
    HiringDecisionAssessmentPanel,
    HiringDecisionCandidateProfile,
    HiringDecisionDetailResult,
    HiringDecisionDimensionItem,
    HiringDecisionInterviewerReviewItem,
    HiringDecisionOperationLogItem,
    HiringDecisionOverview,
    HiringDecisionQAItem,
    HiringDecisionTimelineItem,
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
            daily_deltas=self._build_dashboard_daily_deltas(),
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

    def get_hiring_decision_detail(self, *, job_id: str, candidate_id: str) -> HiringDecisionDetailResult:
        workspace_id = get_workspace_id(self._session)

        pair_stmt = (
            select(JobCandidate, Candidate, Job)
            .join(Candidate, Candidate.id == JobCandidate.candidate_id)
            .join(Job, Job.id == JobCandidate.job_id)
            .where(
                JobCandidate.job_id == job_id,
                JobCandidate.candidate_id == candidate_id,
            )
        )
        if workspace_id:
            pair_stmt = pair_stmt.where(
                Candidate.workspace_id == workspace_id,
                Job.workspace_id == workspace_id,
            )
        pair_row = self._session.execute(pair_stmt).first()
        if pair_row is None:
            raise ResourceNotFoundError(f"Candidate '{candidate_id}' under job '{job_id}' was not found")
        job_candidate, candidate, job = pair_row

        eval_stmt = (
            select(CandidateJobEvaluation)
            .where(
                CandidateJobEvaluation.job_id == job_id,
                CandidateJobEvaluation.candidate_id == candidate_id,
                CandidateJobEvaluation.status.in_(("completed", "reviewed")),
            )
            .order_by(CandidateJobEvaluation.updated_at.desc(), CandidateJobEvaluation.created_at.desc())
            .limit(1)
        )
        if workspace_id:
            eval_stmt = eval_stmt.where(CandidateJobEvaluation.workspace_id == workspace_id)
        evaluation = self._session.execute(eval_stmt).scalars().first()
        if evaluation is None:
            raise ResourceNotFoundError(f"Evaluation for candidate '{candidate_id}' under job '{job_id}' was not found")

        pipeline_stmt = select(CandidateJobPipeline).where(
            CandidateJobPipeline.job_id == job_id,
            CandidateJobPipeline.candidate_id == candidate_id,
        )
        if workspace_id:
            pipeline_stmt = pipeline_stmt.where(CandidateJobPipeline.workspace_id == workspace_id)
        pipeline = self._session.execute(pipeline_stmt).scalars().first()

        session_stmt = (
            select(AIInterviewSession)
            .where(
                AIInterviewSession.job_id == job_id,
                AIInterviewSession.candidate_id == candidate_id,
            )
            .order_by(AIInterviewSession.created_at.desc())
            .limit(1)
        )
        if workspace_id:
            session_stmt = session_stmt.where(AIInterviewSession.workspace_id == workspace_id)
        interview_session = self._session.execute(session_stmt).scalars().first()

        interview_assessment = self._get_latest_interview_assessment(
            session_id=interview_session.id if interview_session else None,
            assessment_id=pipeline.latest_interview_assessment_id if pipeline else None,
        )
        report = self._get_latest_interview_report(interview_session.id if interview_session else None)

        composite_stmt = (
            select(CandidateCompositeAssessment)
            .where(
                CandidateCompositeAssessment.job_id == job_id,
                CandidateCompositeAssessment.candidate_id == candidate_id,
            )
            .order_by(CandidateCompositeAssessment.created_at.desc())
            .limit(1)
        )
        composite = self._session.execute(composite_stmt).scalars().first()

        delivery_stmt = (
            select(CandidateEmailDelivery)
            .where(
                CandidateEmailDelivery.job_id == job_id,
                CandidateEmailDelivery.candidate_id == candidate_id,
            )
            .order_by(CandidateEmailDelivery.created_at.desc())
            .limit(50)
        )
        if workspace_id:
            delivery_stmt = delivery_stmt.where(
                or_(
                    CandidateEmailDelivery.workspace_id == workspace_id,
                    CandidateEmailDelivery.workspace_id.is_(None),
                )
            )
        deliveries = list(self._session.execute(delivery_stmt).scalars().all())

        decision_events: list[DecisionEvent] = []
        if pipeline is not None:
            decision_events = list(
                self._session.execute(
                    select(DecisionEvent)
                    .where(DecisionEvent.pipeline_id == pipeline.id)
                    .order_by(DecisionEvent.created_at.desc())
                    .limit(50)
                ).scalars().all()
            )

        qa_items = self._list_qa_items(session_id=interview_session.id if interview_session else None)

        resume_score = float(evaluation.match_score or 0)
        interview_score = float(
            interview_assessment.total_score
            if interview_assessment is not None
            else (
                report.dimension_scores_json.get("total", evaluation.competitiveness_score or 0)
                if report is not None
                else (evaluation.competitiveness_score or 0)
            )
        )
        composite_score = float(composite.final_score if composite is not None else evaluation.final_score or 0)

        profile = HiringDecisionCandidateProfile(
            candidate_id=candidate.id,
            candidate_name=candidate.name,
            avatar_url=self._pick_avatar_url(candidate.raw_profile),
            phone=self._pick_phone(candidate.raw_profile),
            email=candidate.email,
            city=self._pick_city(candidate, job),
            degree=candidate.degree,
            work_experience=candidate.work_experience,
            current_role=self._pick_role(candidate.raw_profile),
            current_stage=job_candidate.stage or candidate.current_stage,
            expected_salary=candidate.expected_salary,
            applied_at=self._dt(job_candidate.applied_at or job_candidate.first_synced_at),
            updated_at=self._dt(job_candidate.last_synced_at),
            job_id=job.id,
            job_title=job.title,
            department=job.department,
            job_city=job.city,
            job_salary_range=job.salary_range,
        )
        overview = HiringDecisionOverview(
            resume_score=resume_score,
            interview_score=interview_score,
            composite_score=composite_score,
            grade=self._grade_text(composite_score),
            recommendation=str(composite.recommendation if composite is not None else evaluation.recommendation or "review"),
            recommended_salary=candidate.expected_salary or job.salary_range,
            updated_at=self._dt(
                (composite.updated_at if composite is not None else None)
                or (interview_assessment.updated_at if interview_assessment is not None else None)
                or evaluation.updated_at
            ),
        )
        resume_assessment = HiringDecisionAssessmentPanel(
            score=resume_score,
            summary=evaluation.summary,
            dimensions=self._to_dimensions(evaluation.dimension_scores, domain="resume"),
            strengths=[str(item) for item in list(evaluation.strengths or []) if str(item).strip()],
            weaknesses=[str(item) for item in list(evaluation.weaknesses or []) if str(item).strip()],
            risk_tags=[str(item) for item in list(evaluation.risk_flags or []) if str(item).strip()],
        )
        interview_assessment_panel = HiringDecisionAssessmentPanel(
            score=interview_score,
            summary=(
                interview_assessment.summary
                if interview_assessment is not None and interview_assessment.summary
                else (report.summary if report is not None else None)
            ),
            dimensions=self._to_interview_dimensions(interview_assessment, report),
            strengths=[str(item) for item in list(interview_assessment.strengths_json or []) if str(item).strip()]
            if interview_assessment is not None
            else [],
            weaknesses=[str(item) for item in list(interview_assessment.gaps_json or []) if str(item).strip()]
            if interview_assessment is not None
            else [],
            risk_tags=[str(item) for item in list(interview_assessment.risk_flags_json or []) if str(item).strip()]
            if interview_assessment is not None
            else [str(item) for item in list(report.risk_tags_json or []) if str(item).strip()] if report is not None else [],
        )
        composite_assessment = HiringDecisionAssessmentPanel(
            score=composite_score,
            summary=composite.summary if composite is not None else evaluation.summary,
            dimensions=self._to_composite_dimensions(composite),
            risk_tags=[str(item) for item in list(composite.risk_flags_json or []) if str(item).strip()]
            if composite is not None
            else [],
        )
        timeline = self._build_timeline(
            job_candidate=job_candidate,
            deliveries=deliveries,
            decision_events=decision_events,
            pipeline=pipeline,
            overview=overview,
        )
        interviewer_reviews = self._build_interviewer_reviews(
            interview_assessment=interview_assessment,
            report=report,
            deliveries=deliveries,
        )
        operation_logs = self._build_operation_logs(deliveries=deliveries, decision_events=decision_events)
        return HiringDecisionDetailResult(
            profile=profile,
            overview=overview,
            resume_assessment=resume_assessment,
            interview_assessment=interview_assessment_panel,
            composite_assessment=composite_assessment,
            timeline=timeline,
            interviewer_reviews=interviewer_reviews,
            qa_items=qa_items,
            operation_logs=operation_logs,
        )

    def _get_latest_interview_assessment(
        self,
        *,
        session_id: str | None,
        assessment_id: str | None,
    ) -> AIInterviewAssessment | None:
        if assessment_id:
            entity = self._session.get(AIInterviewAssessment, assessment_id)
            if entity is not None:
                return entity
        if not session_id:
            return None
        return self._session.execute(
            select(AIInterviewAssessment)
            .where(AIInterviewAssessment.session_id == session_id)
            .order_by(AIInterviewAssessment.evaluated_at.desc(), AIInterviewAssessment.created_at.desc())
            .limit(1)
        ).scalars().first()

    def _get_latest_interview_report(self, session_id: str | None) -> AIInterviewReport | None:
        if not session_id:
            return None
        return self._session.execute(
            select(AIInterviewReport)
            .where(AIInterviewReport.session_id == session_id)
            .order_by(AIInterviewReport.report_version.desc(), AIInterviewReport.created_at.desc())
            .limit(1)
        ).scalars().first()

    def _list_qa_items(self, *, session_id: str | None) -> list[HiringDecisionQAItem]:
        if not session_id:
            return []
        turns = list(
            self._session.execute(
                select(AIInterviewTurn)
                .where(AIInterviewTurn.session_id == session_id)
                .order_by(AIInterviewTurn.turn_no.asc(), AIInterviewTurn.created_at.asc())
                .limit(200)
            ).scalars().all()
        )
        items: list[HiringDecisionQAItem] = []
        question_buffer: str | None = None
        question_turn_no: int | None = None
        question_time: str | None = None
        for turn in turns:
            speaker = str(turn.speaker or "").strip().lower()
            text = str(turn.transcript or "").strip()
            if not text:
                continue
            if speaker in {"assistant", "interviewer", "ai"}:
                question_buffer = text
                question_turn_no = turn.turn_no
                question_time = self._dt(turn.created_at)
                continue
            if speaker in {"candidate", "user", "human"} and question_buffer:
                items.append(
                    HiringDecisionQAItem(
                        question=question_buffer,
                        answer=text,
                        turn_no=question_turn_no,
                        occurred_at=question_time,
                    )
                )
                question_buffer = None
                question_turn_no = None
                question_time = None
        return items[:50]

    def _build_timeline(
        self,
        *,
        job_candidate: JobCandidate,
        deliveries: list[CandidateEmailDelivery],
        decision_events: list[DecisionEvent],
        pipeline: CandidateJobPipeline | None,
        overview: HiringDecisionOverview,
    ) -> list[HiringDecisionTimelineItem]:
        timeline: list[HiringDecisionTimelineItem] = [
            HiringDecisionTimelineItem(step="简历筛选", time=self._dt(job_candidate.first_synced_at), status="通过"),
        ]
        interview_deliveries = [item for item in deliveries if str(item.scene or "") == "interview_invitation"]
        if interview_deliveries:
            newest = sorted(interview_deliveries, key=lambda item: item.created_at or datetime.min, reverse=True)
            for idx, item in enumerate(newest[:3]):
                timeline.append(
                    HiringDecisionTimelineItem(
                        step=f"面试环节 {idx + 1}",
                        time=self._dt(item.created_at),
                        status=self._delivery_status_text(item.status),
                    )
                )
        if decision_events:
            latest_decision = max(decision_events, key=lambda item: item.created_at or datetime.min)
            timeline.append(
                HiringDecisionTimelineItem(
                    step="录用决策",
                    time=self._dt(latest_decision.created_at),
                    status=str(latest_decision.decision or ""),
                )
            )
        elif pipeline and pipeline.latest_decision_at:
            timeline.append(
                HiringDecisionTimelineItem(
                    step="录用决策",
                    time=self._dt(pipeline.latest_decision_at),
                    status=overview.recommendation,
                )
            )
        return timeline

    def _build_interviewer_reviews(
        self,
        *,
        interview_assessment: AIInterviewAssessment | None,
        report: AIInterviewReport | None,
        deliveries: list[CandidateEmailDelivery],
    ) -> list[HiringDecisionInterviewerReviewItem]:
        reviews: list[HiringDecisionInterviewerReviewItem] = []
        payload = dict(report.payload or {}) if report is not None else {}
        raw_reviews = payload.get("interviewer_reviews")
        if isinstance(raw_reviews, list):
            for item in raw_reviews:
                if not isinstance(item, dict):
                    continue
                reviews.append(
                    HiringDecisionInterviewerReviewItem(
                        reviewer=str(item.get("reviewer") or "面试官"),
                        stage=str(item.get("stage") or ""),
                        score=self._to_float_or_none(item.get("score")),
                        time=str(item.get("time") or ""),
                        comment=str(item.get("comment") or ""),
                    )
                )
        if reviews:
            return reviews[:10]
        if interview_assessment is not None:
            reviews.append(
                HiringDecisionInterviewerReviewItem(
                    reviewer="AI 面试官",
                    stage="综合面试",
                    score=float(interview_assessment.total_score or 0),
                    time=self._dt(interview_assessment.evaluated_at),
                    comment=str(interview_assessment.summary or "综合表现良好"),
                )
            )
        if not reviews and deliveries:
            latest = max(deliveries, key=lambda item: item.created_at or datetime.min)
            reviews.append(
                HiringDecisionInterviewerReviewItem(
                    reviewer="流程系统",
                    stage="邀约记录",
                    score=None,
                    time=self._dt(latest.created_at),
                    comment=str(latest.subject or "已发起面试邀约"),
                )
            )
        return reviews

    def _build_operation_logs(
        self,
        *,
        deliveries: list[CandidateEmailDelivery],
        decision_events: list[DecisionEvent],
    ) -> list[HiringDecisionOperationLogItem]:
        logs: list[HiringDecisionOperationLogItem] = []
        for event in decision_events:
            logs.append(
                HiringDecisionOperationLogItem(
                    type="decision_event",
                    title=str(event.event_type or "decision_event"),
                    status=str(event.decision or ""),
                    time=self._dt(event.created_at),
                    detail=str(event.reason_text or event.reason_code or ""),
                )
            )
        for delivery in deliveries:
            logs.append(
                HiringDecisionOperationLogItem(
                    type="email_delivery",
                    title=str(delivery.subject or "邀请邮件"),
                    status=str(delivery.status or ""),
                    time=self._dt(delivery.created_at),
                    detail=str(delivery.scene or ""),
                )
            )
        logs.sort(key=lambda item: self._to_sort_key(item.time), reverse=True)
        return logs[:80]

    def _to_dimensions(self, raw: dict | None, *, domain: str) -> list[HiringDecisionDimensionItem]:
        labels_resume = {
            "education_match": "教育背景",
            "skill_match": "专业技能",
            "project_relevance": "项目经验",
            "experience_depth": "实习经历",
            "competitiveness": "综合素质",
            "education": "教育背景",
            "projects": "项目经历",
            "skills": "专业技能",
            "learning_agility": "学习潜力",
            "potential": "学习潜力",
            "experience": "团队协作能力",
            "jd_coverage": "解决问题能力",
            "evidence_quality": "代码能力",
            "engineering_ability": "专业技能",
            "requirement_strictness": "解决问题能力",
            "risk_penalty": "风险控制",
        }
        labels_interview = {
            "competency": "专业技能",
            "communication": "沟通表达能力",
            "consistency": "问题解决能力",
            "stability": "团队协作能力",
            "risk_penalty": "风险控制",
            "education": "教育背景",
            "projects": "项目经历",
            "skills": "专业技能",
            "learning_agility": "学习潜力",
            "potential": "学习潜力",
            "experience": "团队协作能力",
            "jd_coverage": "问题解决能力",
            "evidence_quality": "代码能力",
            "engineering_ability": "专业技能",
            "requirement_strictness": "问题解决能力",
        }
        benchmark_scores = {
            "education_match": 75.0,
            "skill_match": 80.0,
            "project_relevance": 80.0,
            "experience_depth": 75.0,
            "competitiveness": 75.0,
            "competency": 80.0,
            "communication": 75.0,
            "consistency": 80.0,
            "stability": 75.0,
            "risk_penalty": 75.0,
            "education": 75.0,
            "projects": 80.0,
            "skills": 80.0,
            "learning_agility": 75.0,
            "potential": 75.0,
            "experience": 75.0,
            "jd_coverage": 80.0,
            "evidence_quality": 80.0,
            "engineering_ability": 80.0,
            "requirement_strictness": 80.0,
        }
        labels = labels_resume if domain == "resume" else labels_interview
        rows: list[HiringDecisionDimensionItem] = []
        source = dict(raw or {})
        for key, value in source.items():
            score = self._to_float_or_none(value)
            if score is None:
                continue
            raw_key = str(key).strip().lower()
            normalized_key = (
                raw_key.replace("-", "_")
                .replace(" ", "_")
                .replace("__", "_")
                .replace("__", "_")
            )
            rows.append(
                HiringDecisionDimensionItem(
                    key=normalized_key,
                    label=labels.get(normalized_key, self._labelize(normalized_key)),
                    score=round(score, 2),
                    max_score=float(benchmark_scores.get(normalized_key, 100.0)),
                )
            )
        rows.sort(key=lambda item: item.score, reverse=True)
        return rows

    def _to_interview_dimensions(
        self,
        interview_assessment: AIInterviewAssessment | None,
        report: AIInterviewReport | None,
    ) -> list[HiringDecisionDimensionItem]:
        if interview_assessment is not None:
            source = {
                "competency": float(interview_assessment.competency_score or 0),
                "communication": float(interview_assessment.communication_score or 0),
                "consistency": float(interview_assessment.consistency_score or 0),
                "stability": float(interview_assessment.stability_score or 0),
                "risk_penalty": max(0.0, 100.0 - float(interview_assessment.risk_penalty_score or 0)),
            }
            return self._to_dimensions(source, domain="interview")
        if report is not None:
            return self._to_dimensions(dict(report.dimension_scores_json or {}), domain="interview")
        return []

    def _to_composite_dimensions(
        self,
        composite: CandidateCompositeAssessment | None,
    ) -> list[HiringDecisionDimensionItem]:
        if composite is None:
            return []
        return [
            HiringDecisionDimensionItem(key="resume_score", label="简历评分", score=round(float(composite.resume_score or 0), 2)),
            HiringDecisionDimensionItem(key="interview_score", label="面试评分", score=round(float(composite.interview_score or 0), 2)),
            HiringDecisionDimensionItem(key="market_score", label="市场匹配", score=round(float(composite.market_score or 0), 2)),
            HiringDecisionDimensionItem(key="stability_score", label="稳定性", score=round(float(composite.stability_score or 0), 2)),
        ]

    def _pick_avatar_url(self, raw_profile: dict | None) -> str | None:
        raw = dict(raw_profile or {})
        for key in ("avatar_url", "avatar", "photo", "head_img"):
            text = str(raw.get(key) or "").strip()
            if text:
                return text
        return None

    def _pick_phone(self, raw_profile: dict | None) -> str | None:
        raw = dict(raw_profile or {})
        for key in ("mobile", "phone", "phone_number"):
            text = str(raw.get(key) or "").strip()
            if text:
                return text
        return None

    def _pick_city(self, candidate: Candidate, job: Job) -> str | None:
        raw = dict(candidate.raw_profile or {})
        city = str(raw.get("city") or "").strip()
        return city or job.city

    def _pick_role(self, raw_profile: dict | None) -> str | None:
        raw = dict(raw_profile or {})
        for key in ("role", "title", "position", "current_role"):
            text = str(raw.get(key) or "").strip()
            if text:
                return text
        return None

    def _grade_text(self, score: float) -> str:
        if score >= 85:
            return "优秀"
        if score >= 75:
            return "良好"
        if score >= 65:
            return "中等"
        return "待提升"

    def _delivery_status_text(self, status: str | None) -> str:
        val = str(status or "").strip().lower()
        mapping = {
            "pending": "待发送",
            "sending": "发送中",
            "sent": "已发送",
            "delivered": "已送达",
            "opened": "已打开",
            "clicked": "已完成",
            "failed": "失败",
        }
        return mapping.get(val, status or "--")

    def _labelize(self, key: str) -> str:
        return key.replace("_", " ").strip().title()

    def _dt(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.isoformat()

    def _to_float_or_none(self, value) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _to_sort_key(self, value: str | None) -> float:
        if not value:
            return 0
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0

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
            avatar_url=self._pick_avatar_url(candidate.raw_profile),
            candidate_stage=candidate.current_stage,
            candidate_expected_salary=candidate.expected_salary,
            candidate_score_explanation=candidate.score_explanation,
            job_id=job.id,
            job_title=job.title,
            job_salary_range=job.salary_range,
            evaluation_status=evaluation.status,
            resume_score=float(evaluation.match_score or 0),
            interview_score=float(evaluation.competitiveness_score or 0),
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

    def _build_dashboard_daily_deltas(self) -> DashboardDailyDelta:
        today_start, tomorrow_start, yesterday_start = self._day_boundaries()
        return DashboardDailyDelta(
            open_jobs=(
                self._count_jobs_created_between(today_start, tomorrow_start)
                - self._count_jobs_created_between(yesterday_start, today_start)
            ),
            total_candidates=(
                self._count_job_candidates_synced_between(today_start, tomorrow_start)
                - self._count_job_candidates_synced_between(yesterday_start, today_start)
            ),
            pending_interviews=(
                self._count_manual_review_evaluations_between(today_start, tomorrow_start)
                - self._count_manual_review_evaluations_between(yesterday_start, today_start)
            ),
            pending_invitations=(
                self._count_invitation_deliveries_created_between(today_start, tomorrow_start)
                - self._count_invitation_deliveries_created_between(yesterday_start, today_start)
            ),
            monthly_hires=(
                self._count_recommended_evaluations_between(today_start, tomorrow_start)
                - self._count_recommended_evaluations_between(yesterday_start, today_start)
            ),
        )

    def _day_boundaries(self) -> tuple[datetime, datetime, datetime]:
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_start = today_start + timedelta(days=1)
        yesterday_start = today_start - timedelta(days=1)
        return today_start, tomorrow_start, yesterday_start

    def _count_jobs_created_between(self, start_at: datetime, end_at: datetime) -> int:
        stmt = select(func.count(Job.id)).where(Job.created_at >= start_at, Job.created_at < end_at)
        workspace_id = get_workspace_id(self._session)
        if workspace_id:
            stmt = stmt.where(Job.workspace_id == workspace_id)
        return int(self._session.execute(stmt).scalar() or 0)

    def _count_job_candidates_synced_between(self, start_at: datetime, end_at: datetime) -> int:
        stmt = select(func.count(JobCandidate.id)).where(
            JobCandidate.first_synced_at >= start_at,
            JobCandidate.first_synced_at < end_at,
        )
        workspace_id = get_workspace_id(self._session)
        if workspace_id:
            stmt = stmt.join(Job, Job.id == JobCandidate.job_id).where(Job.workspace_id == workspace_id)
        return int(self._session.execute(stmt).scalar() or 0)

    def _count_manual_review_evaluations_between(self, start_at: datetime, end_at: datetime) -> int:
        stmt = select(func.count(CandidateJobEvaluation.id)).where(
            CandidateJobEvaluation.created_at >= start_at,
            CandidateJobEvaluation.created_at < end_at,
            CandidateJobEvaluation.status.in_(("completed", "reviewed")),
            CandidateJobEvaluation.recommendation == "manual_review",
        )
        workspace_id = get_workspace_id(self._session)
        if workspace_id:
            stmt = stmt.where(CandidateJobEvaluation.workspace_id == workspace_id)
        return int(self._session.execute(stmt).scalar() or 0)

    def _count_recommended_evaluations_between(self, start_at: datetime, end_at: datetime) -> int:
        stmt = select(func.count(CandidateJobEvaluation.id)).where(
            CandidateJobEvaluation.created_at >= start_at,
            CandidateJobEvaluation.created_at < end_at,
            CandidateJobEvaluation.status.in_(("completed", "reviewed")),
            CandidateJobEvaluation.recommendation.in_(("recommend", "strong_recommend")),
        )
        workspace_id = get_workspace_id(self._session)
        if workspace_id:
            stmt = stmt.where(CandidateJobEvaluation.workspace_id == workspace_id)
        return int(self._session.execute(stmt).scalar() or 0)

    def _count_invitation_deliveries_created_between(self, start_at: datetime, end_at: datetime) -> int:
        stmt = select(func.count(CandidateEmailDelivery.id)).where(
            CandidateEmailDelivery.scene == "interview_invitation",
            CandidateEmailDelivery.created_at >= start_at,
            CandidateEmailDelivery.created_at < end_at,
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


def get_analytics_service(session: Session) -> AnalyticsService:
    return AnalyticsService(session)
