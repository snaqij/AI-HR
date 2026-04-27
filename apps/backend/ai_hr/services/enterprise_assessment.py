"""Enterprise-grade interview and composite assessment service."""

from __future__ import annotations

import math
import re
import statistics
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.orm import Session

from ..core.exceptions import InvalidStateError, ResourceNotFoundError
from ..db.models import (
    AIInterviewAnswerRecord,
    AIInterviewAnswerScore,
    AIInterviewAssessment,
    AIInterviewQuestionAttempt,
    AIInterviewSession,
    AIInterviewTurn,
    Candidate,
    CandidateCompositeAssessment,
    CandidateJobEvaluation,
    CandidateJobPipeline,
    DecisionEvent,
    DecisionPolicyVersion,
    Job,
    JobMarketSnapshot,
    ReviewQueueTask,
)
from ..repositories.events import EventRepository
from ..schemas.ai_assessments import (
    CompositeAssessmentComputeRequest,
    CompositeDecisionRequest,
    CompositeDecisionResponse,
    CompositeOverrideRequest,
    CompositeOverrideResponse,
    InterviewAssessmentLatestResponse,
    ReviewQueueTaskItem,
    ReviewQueueTaskListResponse,
)

QUESTION_SCORE_WEIGHTS = {
    "completeness": 0.22,
    "depth": 0.20,
    "evidence": 0.20,
    "logic": 0.14,
    "communication": 0.10,
    "domain_fit": 0.14,
}

DEFAULT_STAGE_WEIGHTS = {
    "opening": 0.8,
    "self_intro": 0.9,
    "tech_stack": 1.0,
    "project_deep_dive": 1.2,
    "jd_match": 1.2,
    "general_probe": 1.0,
    "company_qa": 0.7,
}

DEFAULT_DIFFICULTY_WEIGHTS = {"easy": 0.9, "medium": 1.0, "hard": 1.1}
REDLINE_RISK_TAGS = {"identity_fraud", "compliance_block", "severe_security"}


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _next_version(existing: list[str]) -> str:
    nums: list[int] = []
    for item in existing:
        match = re.match(r"^v(\d+)$", str(item or "").strip())
        if match:
            nums.append(int(match.group(1)))
    return f"v{(max(nums) if nums else 0) + 1}"


def _compute_age_minutes(created_at: datetime | None, now: datetime) -> int:
    if created_at is None:
        return 0
    delta = now - created_at.replace(tzinfo=None)
    return max(0, int(delta.total_seconds() // 60))


@dataclass(slots=True)
class _AnswerScorePack:
    question_score: float
    reliability: float
    question_weight: float
    risk_penalty: float
    model_confidence: float
    evidence_density: float
    dimensions: dict[str, float]
    risk_tags: list[str]
    evidence_refs: list[dict[str, Any]]


class EnterpriseAssessmentService:
    """Service for event mapping, interview assessment, and composite decisioning."""

    def __init__(self, session: Session, llm_client: Any = None):
        self._session = session
        self._event_repository = EventRepository(session)
        self._llm_client = llm_client

    def bind_question_answer_from_turn(
        self,
        *,
        session_id: str,
        turn: AIInterviewTurn,
        request_payload: dict[str, Any] | None,
        interview_stage: str | None,
        commit: bool = True,
    ) -> str | None:
        payload = dict(request_payload or {})
        question_id = str(
            payload.get("current_question_id")
            or payload.get("question_id")
            or turn.question_id
            or ""
        ).strip()
        if not question_id:
            return None

        question_seq_raw = (
            payload.get("current_question_seq")
            or payload.get("question_seq")
            or turn.question_seq
            or turn.turn_no
        )
        try:
            question_seq = max(1, int(question_seq_raw))
        except (TypeError, ValueError):
            question_seq = max(1, int(turn.turn_no))

        question_text = str(
            payload.get("current_question_text")
            or payload.get("question_text")
            or payload.get("question")
            or f"Question {question_seq}"
        ).strip()
        question_type = str(payload.get("question_type") or "mixed").strip() or "mixed"
        competency_code = str(payload.get("competency_code") or "").strip() or None
        difficulty_level = str(payload.get("difficulty_level") or "medium").strip() or "medium"
        ingest_trace_id = str(payload.get("trace_id") or turn.ingest_trace_id or "").strip() or None

        attempt = self._session.execute(
            select(AIInterviewQuestionAttempt)
            .where(
                AIInterviewQuestionAttempt.session_id == session_id,
                AIInterviewQuestionAttempt.question_id == question_id,
            )
            .order_by(desc(AIInterviewQuestionAttempt.created_at))
            .limit(1)
        ).scalars().first()

        if attempt is None:
            attempt = AIInterviewQuestionAttempt(
                session_id=session_id,
                question_set_id=None,
                question_id=question_id,
                question_seq=question_seq,
                question_type=question_type,
                competency_code=competency_code,
                difficulty_level=difficulty_level,
                question_text=question_text,
                asked_turn_id=turn.id if turn.speaker != "candidate" else None,
                asked_at=_now(),
                status="asking" if turn.speaker != "candidate" else "answered",
                timeout_seconds=None,
                context_payload={
                    "stage": interview_stage,
                    "required": payload.get("required", True),
                    "critical": payload.get("critical", False),
                },
                payload={},
            )
            self._session.add(attempt)
            self._session.flush()
        else:
            attempt.question_seq = attempt.question_seq or question_seq
            attempt.question_text = attempt.question_text or question_text
            attempt.question_type = attempt.question_type or question_type
            if attempt.asked_turn_id is None and turn.speaker != "candidate":
                attempt.asked_turn_id = turn.id

        if turn.speaker != "candidate":
            attempt.status = "asking"
        else:
            next_answer_no = int(
                self._session.execute(
                    select(func.max(AIInterviewAnswerRecord.answer_no)).where(
                        AIInterviewAnswerRecord.question_attempt_id == attempt.id
                    )
                ).scalar_one()
                or 0
            ) + 1

            answer = AIInterviewAnswerRecord(
                question_attempt_id=attempt.id,
                session_id=session_id,
                answer_no=next_answer_no,
                answer_turn_id=turn.id,
                answer_text=(turn.transcript or "").strip() or None,
                answer_language=str(payload.get("language") or "").strip() or None,
                source=str(payload.get("source") or "voice"),
                asr_confidence=turn.confidence,
                answer_duration_ms=payload.get("answer_duration_ms"),
                answer_started_at=None,
                answer_ended_at=None,
                is_final=bool(payload.get("is_final_answer", True)),
                ingest_trace_id=ingest_trace_id,
                payload={"event_payload": payload},
            )
            self._session.add(answer)
            self._session.flush()

            if bool(payload.get("invalid_answer")):
                attempt.status = "invalid"
            elif bool(payload.get("need_followup")):
                attempt.status = "needs_followup"
            elif bool(payload.get("is_final_answer", True)):
                attempt.status = "completed"
            else:
                attempt.status = "answered"

            merged_attempt_payload = dict(attempt.payload or {})
            merged_attempt_payload["last_answer_record_id"] = answer.id
            attempt.payload = merged_attempt_payload

        turn.question_attempt_id = attempt.id
        turn.question_id = question_id
        turn.question_seq = question_seq
        turn.ingest_trace_id = ingest_trace_id
        self._session.flush()
        if commit:
            self._session.commit()
        return attempt.id

    def compute_interview_assessment(
        self,
        *,
        session_id: str,
        run_mode: str,
        policy_code: str,
        policy_version: str | None,
        force_recompute: bool,
    ) -> tuple[AIInterviewAssessment, str | None]:
        queue_id = str(uuid.uuid4()) if run_mode == "async" else None
        self._emit_async_event(
            event_type="interview.assessment.requested",
            entity_type="ai_interview_session",
            entity_id=session_id,
            session_id=session_id,
            payload={
                "policy_code": policy_code,
                "policy_version": policy_version,
                "force_recompute": force_recompute,
                "queue_id": queue_id,
            },
        )

        self._ensure_session_exists(session_id)
        self._backfill_question_answer_records(session_id=session_id)
        latest = self._get_latest_interview_assessment(session_id=session_id)
        if latest is not None and not force_recompute:
            return latest, queue_id

        attempts = list(
            self._session.execute(
                select(AIInterviewQuestionAttempt)
                .where(AIInterviewQuestionAttempt.session_id == session_id)
                .order_by(AIInterviewQuestionAttempt.question_seq.asc(), AIInterviewQuestionAttempt.created_at.asc())
            ).scalars().all()
        )
        if not attempts:
            raise InvalidStateError(f"No question attempts found for session '{session_id}'")

        total_required = 0
        answered_required = 0
        question_scores: list[float] = []
        reliabilities: list[float] = []
        risk_penalties: list[float] = []
        competency_values: list[float] = []
        communication_values: list[float] = []
        evidence_refs: list[dict[str, Any]] = []
        risk_tags: list[str] = []
        critical_scores: list[float] = []
        weighted_sum = 0.0
        weighted_base = 0.0
        score_version = f"enterprise-{_now().strftime('%Y%m%d%H%M%S')}"

        for attempt in attempts:
            required = bool((attempt.context_payload or {}).get("required", True))
            if required:
                total_required += 1

            answer = self._session.execute(
                select(AIInterviewAnswerRecord)
                .where(AIInterviewAnswerRecord.question_attempt_id == attempt.id)
                .order_by(
                    AIInterviewAnswerRecord.is_final.desc(),
                    AIInterviewAnswerRecord.answer_no.desc(),
                    AIInterviewAnswerRecord.created_at.desc(),
                )
                .limit(1)
            ).scalars().first()

            if answer is None or not (answer.answer_text or "").strip():
                if attempt.status in {"asking", "pending"}:
                    attempt.status = "abandoned"
                continue

            if required:
                answered_required += 1

            score_pack = self._score_answer(attempt=attempt, answer=answer)
            question_scores.append(score_pack.question_score)
            reliabilities.append(score_pack.reliability)
            risk_penalties.append(score_pack.risk_penalty)
            competency_values.extend(
                [
                    score_pack.dimensions["completeness"],
                    score_pack.dimensions["depth"],
                    score_pack.dimensions["evidence"],
                    score_pack.dimensions["logic"],
                    score_pack.dimensions["domain_fit"],
                ]
            )
            communication_values.append(score_pack.dimensions["communication"])
            evidence_refs.extend(score_pack.evidence_refs)
            risk_tags.extend(score_pack.risk_tags)
            weighted_sum += score_pack.question_score * score_pack.reliability * score_pack.question_weight
            weighted_base += score_pack.reliability * score_pack.question_weight

            if bool((attempt.context_payload or {}).get("critical")):
                critical_scores.append(score_pack.question_score)

            score_entity = AIInterviewAnswerScore(
                answer_record_id=answer.id,
                question_attempt_id=attempt.id,
                score_version=score_version,
                scoring_model="enterprise_interview_rubric_v1",
                status="final",
                overall_score=round(score_pack.question_score, 2),
                content_score=round(score_pack.dimensions["completeness"], 2),
                reasoning_score=round(score_pack.dimensions["logic"], 2),
                communication_score=round(score_pack.dimensions["communication"], 2),
                relevance_score=round(score_pack.dimensions["domain_fit"], 2),
                confidence_score=round(score_pack.model_confidence * 100.0, 2),
                risk_penalty_score=round(score_pack.risk_penalty, 2),
                strengths_json=[],
                gaps_json=[],
                risk_flags_json=score_pack.risk_tags,
                evidence_json=score_pack.evidence_refs,
                explanation="Enterprise rubric scoring for answer quality and reliability.",
                scored_at=_now(),
                payload={
                    "reliability": score_pack.reliability,
                    "evidence_density": score_pack.evidence_density,
                    "question_weight": score_pack.question_weight,
                },
            )
            self._session.add(score_entity)

        coverage_rate = (answered_required / total_required) if total_required > 0 else 0.0
        interview_score = (weighted_sum / weighted_base) if weighted_base > 0 else 0.0
        mean_reliability = statistics.fmean(reliabilities) if reliabilities else 0.0
        interview_confidence = math.sqrt(_clip(mean_reliability * coverage_rate, 0.0, 1.0))

        competency_score = statistics.fmean(competency_values) if competency_values else 0.0
        communication_score = statistics.fmean(communication_values) if communication_values else 0.0
        consistency_score = _clip(
            100.0 - (statistics.pstdev(question_scores) * 1.6 if len(question_scores) > 1 else 0.0),
            0.0,
            100.0,
        )
        stability_score = _clip(interview_confidence * 100.0, 0.0, 100.0)
        risk_penalty_score = statistics.fmean(risk_penalties) if risk_penalties else 0.0

        unique_risks = sorted({str(tag) for tag in risk_tags if str(tag).strip()})
        recommendation, hard_fail, must_review, decision_reasons = self._decide_by_rules(
            composite_score=interview_score,
            composite_confidence=interview_confidence,
            risk_tags=unique_risks,
            critical_min_score=min(critical_scores) if critical_scores else None,
            coverage_rate=coverage_rate,
            interview_confidence=interview_confidence,
        )

        # Generate AI summary using LLM
        summary_text = "面试评估已完成，综合表现有待进一步分析。"
        strengths_list: list[str] = []
        gaps_list: list[str] = []
        
        if self._llm_client is not None:
            try:
                # Get session and candidate info
                session_entity = self._session.get(AIInterviewSession, session_id)
                candidate_name = "候选人"
                job_title = "目标岗位"
                
                if session_entity:
                    if session_entity.candidate_id:
                        candidate = self._session.get(Candidate, session_entity.candidate_id)
                        if candidate:
                            candidate_name = candidate.name or "候选人"
                    if session_entity.job_id:
                        job = self._session.get(Job, session_entity.job_id)
                        if job:
                            job_title = job.title or "目标岗位"
                
                # Build QA summary (first 5 questions for context)
                qa_parts = []
                for idx, attempt in enumerate(attempts[:5], 1):
                    answer = self._session.execute(
                        select(AIInterviewAnswerRecord)
                        .where(AIInterviewAnswerRecord.question_attempt_id == attempt.id)
                        .order_by(AIInterviewAnswerRecord.is_final.desc(), AIInterviewAnswerRecord.created_at.desc())
                        .limit(1)
                    ).scalars().first()
                    
                    if answer and answer.answer_text:
                        q_text = (attempt.question_text or "")[:100]
                        a_text = (answer.answer_text or "")[:200]
                        qa_parts.append(f"Q{idx}: {q_text}\nA{idx}: {a_text}")
                
                qa_summary = "\n\n".join(qa_parts) if qa_parts else "无详细问答记录"
                
                from .llm.client import InvokeContext
                from .llm.prompts import get_prompt_template
                
                template = get_prompt_template("interview_summary", "v1")
                context = InvokeContext(
                    task_key="interview_summary",
                    trace_id=f"summary-{session_id}-{uuid.uuid4().hex[:8]}",
                    prompt=template.render(
                        candidate_name=candidate_name,
                        job_title=job_title,
                        total_score=interview_score,
                        competency_score=competency_score,
                        communication_score=communication_score,
                        consistency_score=consistency_score,
                        stability_score=stability_score,
                        coverage_rate=coverage_rate,
                        question_count=total_required,
                        answered_count=answered_required,
                        risk_tags=", ".join(unique_risks) if unique_risks else "无",
                        qa_summary=qa_summary,
                    ),
                    system_prompt=template.system_prompt,
                )
                
                llm_result = self._llm_client.invoke_json(context)
                data = llm_result.content
                
                if isinstance(data, dict) and not data.get("error"):
                    summary_text = data.get("summary", summary_text)
                    strengths_list = data.get("strengths", [])
                    gaps_list = data.get("gaps", [])
                    
                    # Ensure lists are valid
                    if not isinstance(strengths_list, list):
                        strengths_list = []
                    if not isinstance(gaps_list, list):
                        gaps_list = []
                        
            except Exception as llm_exc:
                # Log but don't fail the assessment
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to generate AI summary for session {session_id}: {llm_exc}", exc_info=True)

        versions = list(
            self._session.execute(
                select(AIInterviewAssessment.assessment_version).where(
                    AIInterviewAssessment.session_id == session_id
                )
            ).scalars().all()
        )
        assessment = AIInterviewAssessment(
            session_id=session_id,
            assessment_version=_next_version(versions),
            status="computed",
            evaluated_by="ai",
            scoring_formula_version="interview_enterprise_v1",
            coverage_score=round(coverage_rate * 100.0, 2),
            competency_score=round(competency_score, 2),
            communication_score=round(communication_score, 2),
            consistency_score=round(consistency_score, 2),
            stability_score=round(stability_score, 2),
            risk_penalty_score=round(risk_penalty_score, 2),
            total_score=round(_clip(interview_score, 0.0, 100.0), 2),
            confidence_score=round(interview_confidence * 100.0, 2),
            recommendation=recommendation,
            hard_fail=hard_fail,
            must_review=must_review,
            strengths_json=strengths_list,
            gaps_json=gaps_list,
            risk_flags_json=unique_risks,
            evidence_json=evidence_refs,
            dimension_weights_json=QUESTION_SCORE_WEIGHTS,
            summary=summary_text,
            payload={
                "coverage_rate": round(coverage_rate, 4),
                "interview_confidence": round(interview_confidence, 4),
                "decision_reasons": decision_reasons,
                "policy_code": policy_code,
                "policy_version": policy_version,
            },
            evaluated_at=_now(),
        )
        self._session.add(assessment)
        self._session.flush()
        self._sync_pipeline_after_interview_assessment(session_id=session_id, assessment=assessment)

        self._emit_async_event(
            event_type="interview.assessment.computed",
            entity_type="ai_interview_assessment",
            entity_id=assessment.id,
            session_id=session_id,
            payload={
                "assessment_id": assessment.id,
                "score": float(assessment.total_score),
                "recommendation": assessment.recommendation,
                "queue_id": queue_id,
            },
        )

        self._session.commit()
        self._session.refresh(assessment)
        return assessment, queue_id

    def get_latest_interview_assessment_response(self, *, session_id: str) -> InterviewAssessmentLatestResponse:
        assessment = self._get_latest_interview_assessment(session_id=session_id)
        if assessment is None:
            raise ResourceNotFoundError(f"No interview assessment found for session '{session_id}'")
        payload = dict(assessment.payload or {})
        dimension_scores = {
            "competency": round(_to_float(assessment.competency_score), 2),
            "communication": round(_to_float(assessment.communication_score), 2),
            "consistency": round(_to_float(assessment.consistency_score), 2),
            "stability": round(_to_float(assessment.stability_score), 2),
            "risk_penalty": round(_to_float(assessment.risk_penalty_score), 2),
        }
        return InterviewAssessmentLatestResponse(
            assessment_id=assessment.id,
            interview_score=round(_to_float(assessment.total_score), 2),
            dimension_scores=dimension_scores,
            coverage_rate=round(_to_float(payload.get("coverage_rate"), _to_float(assessment.coverage_score) / 100.0), 4),
            recommendation=assessment.recommendation,
            risk_tags=[str(item) for item in list(assessment.risk_flags_json or [])],
            evidence_refs=[dict(item) for item in list(assessment.evidence_json or []) if isinstance(item, dict)],
        )

    def compute_composite_assessment(self, payload: CompositeAssessmentComputeRequest) -> CandidateCompositeAssessment:
        session_entity = self._ensure_session_exists(payload.session_id)
        if session_entity.candidate_id != payload.candidate_id or session_entity.job_id != payload.job_id:
            raise InvalidStateError("session_id does not match candidate_id/job_id in request")

        pipeline = self._session.execute(
            select(CandidateJobPipeline).where(
                CandidateJobPipeline.candidate_id == payload.candidate_id,
                CandidateJobPipeline.job_id == payload.job_id,
            )
        ).scalars().first()
        if pipeline is None:
            candidate = self._session.get(Candidate, payload.candidate_id)
            if candidate is None:
                raise ResourceNotFoundError(f"Candidate '{payload.candidate_id}' was not found")
            pipeline = CandidateJobPipeline(
                candidate_id=payload.candidate_id,
                job_id=payload.job_id,
                source_channel=candidate.source_channel,
                external_candidate_id=candidate.external_candidate_id,
                resume_request_status="pending",
                resume_download_status="pending",
                evaluation_status="pending",
                invitation_status="not_invited",
                interview_status="not_started",
                composite_assessment_status="pending",
                next_step_status="pending_decision",
                sync_status="active",
                payload={},
            )
            self._session.add(pipeline)
            self._session.flush()

        resume_evaluation = self._resolve_resume_evaluation(
            candidate_id=payload.candidate_id,
            job_id=payload.job_id,
            resume_evaluation_id=payload.resume_evaluation_id,
        )
        interview_assessment = self._get_latest_interview_assessment(session_id=payload.session_id)
        if interview_assessment is None:
            raise InvalidStateError(f"No interview assessment found for session '{payload.session_id}'")

        market_score, market_confidence, market_snapshot_id = self._resolve_market_signal(
            job_id=payload.job_id,
            market_context=(payload.market_context.model_dump() if payload.market_context else {}),
        )
        resume_score = _clip(_to_float(resume_evaluation.final_score), 0.0, 100.0)
        interview_score = _clip(_to_float(interview_assessment.total_score), 0.0, 100.0)
        stability_score = _clip(_to_float(interview_assessment.stability_score), 0.0, 100.0)
        resume_confidence = _clip(_to_float(resume_evaluation.confidence_score, 75.0) / 100.0, 0.0, 1.0)
        interview_confidence = _clip(_to_float(interview_assessment.confidence_score, 60.0) / 100.0, 0.0, 1.0)

        raw_score = 0.40 * resume_score + 0.45 * interview_score + 0.15 * market_score
        risk_tags = sorted(
            {
                str(item)
                for item in (
                    list(resume_evaluation.risk_flags or [])
                    + list(interview_assessment.risk_flags_json or [])
                )
                if str(item).strip()
            }
        )
        global_risk_penalty = _clip(float(len(risk_tags)) * 2.5, 0.0, 30.0)
        bonus = 2.0 if (resume_score >= 85.0 and interview_score >= 88.0 and interview_confidence >= 0.75) else 0.0
        composite_score = _clip(raw_score - global_risk_penalty + bonus, 0.0, 100.0)
        composite_confidence = _clip(
            0.50 * resume_confidence + 0.35 * interview_confidence + 0.15 * market_confidence,
            0.0,
            1.0,
        )
        interview_payload = dict(interview_assessment.payload or {})
        coverage_rate = _to_float(interview_payload.get("coverage_rate"), _to_float(interview_assessment.coverage_score) / 100.0)
        critical_min_score = interview_payload.get("critical_min_score")
        recommendation, hard_reject, must_review, decision_reasons = self._decide_by_rules(
            composite_score=composite_score,
            composite_confidence=composite_confidence,
            risk_tags=risk_tags,
            critical_min_score=_to_float(critical_min_score) if critical_min_score is not None else None,
            coverage_rate=coverage_rate,
            interview_confidence=interview_confidence,
        )
        candidate_entity = self._session.get(Candidate, payload.candidate_id)
        job_entity = self._session.get(Job, payload.job_id)
        compensation_fit = self._evaluate_compensation_fit(
            candidate=candidate_entity,
            job=job_entity,
            resume_evaluation=resume_evaluation,
            interview_assessment=interview_assessment,
            composite_score=composite_score,
        )
        compensation_decision = str(compensation_fit.get("decision") or "").strip().lower()
        if compensation_decision == "not_match":
            if recommendation == "advance":
                recommendation = "manual_review"
                must_review = True
                hard_reject = False
            if "salary_not_match" not in decision_reasons:
                decision_reasons.append("salary_not_match")
        elif compensation_decision == "conditional_match":
            if recommendation == "advance":
                recommendation = "manual_review"
                must_review = True
                hard_reject = False
            if "salary_conditional_match" not in decision_reasons:
                decision_reasons.append("salary_conditional_match")

        policy = self._resolve_policy(policy_code="candidate_progression", policy_version=None)
        versions = list(
            self._session.execute(
                select(CandidateCompositeAssessment.composite_version).where(
                    CandidateCompositeAssessment.pipeline_id == pipeline.id
                )
            ).scalars().all()
        )
        assessment = CandidateCompositeAssessment(
            pipeline_id=pipeline.id,
            candidate_id=payload.candidate_id,
            job_id=payload.job_id,
            evaluation_id=resume_evaluation.id,
            interview_assessment_id=interview_assessment.id,
            market_snapshot_id=market_snapshot_id,
            policy_version_id=policy.id,
            composite_version=_next_version(versions),
            status="completed",
            resume_score=round(resume_score, 2),
            interview_score=round(interview_score, 2),
            market_score=round(market_score, 2),
            stability_score=round(stability_score, 2),
            risk_penalty_score=round(global_risk_penalty, 2),
            final_score=round(composite_score, 2),
            confidence_score=round(composite_confidence * 100.0, 2),
            recommendation=recommendation,
            hard_reject=hard_reject,
            must_review=must_review,
            factor_breakdown_json={
                "raw_score": round(raw_score, 2),
                "bonus": round(bonus, 2),
                "weights": {"resume": 0.40, "interview": 0.45, "market": 0.15},
                "compensation_fit_score": round(_to_float(compensation_fit.get("score"), 60.0), 2),
            },
            risk_flags_json=risk_tags,
            reason_codes_json=decision_reasons,
            summary="Composite assessment computed from resume/interview/market signals.",
            payload={
                "coverage_rate": round(coverage_rate, 4),
                "market_confidence": round(market_confidence, 4),
                "resume_confidence": round(resume_confidence, 4),
                "interview_confidence": round(interview_confidence, 4),
                "compensation_fit": compensation_fit,
            },
            scored_at=_now(),
        )
        self._session.add(assessment)
        self._session.flush()

        pipeline.interview_status = "interview_completed"
        pipeline.composite_assessment_status = "composite_computed"
        pipeline.latest_interview_assessment_id = interview_assessment.id
        pipeline.latest_composite_assessment_id = assessment.id
        pipeline.latest_policy_version_id = policy.id
        pipeline.last_interview_evaluated_at = _now()
        self._session.flush()

        if recommendation == "manual_review":
            self._create_review_task(
                pipeline_id=pipeline.id,
                composite_assessment_id=assessment.id,
                reason_codes=decision_reasons,
                risk_tags=risk_tags,
            )

        self._emit_async_event(
            event_type="composite.assessment.computed",
            entity_type="candidate_composite_assessment",
            entity_id=assessment.id,
            session_id=payload.session_id,
            job_id=payload.job_id,
            payload={
                "candidate_id": payload.candidate_id,
                "pipeline_id": pipeline.id,
                "score": round(composite_score, 2),
                "confidence": round(composite_confidence, 4),
                "recommendation": recommendation,
            },
        )
        self._session.commit()
        self._session.refresh(assessment)
        return assessment

    @staticmethod
    def _normalize_degree_rank(value: str | None) -> int:
        text = str(value or "").strip().lower()
        if not text:
            return 0
        if any(token in text for token in ("博士", "phd", "doctor")):
            return 5
        if any(token in text for token in ("硕士", "master", "研究生")):
            return 4
        if any(token in text for token in ("本科", "bachelor", "学士")):
            return 3
        if any(token in text for token in ("大专", "college", "专科")):
            return 2
        if any(token in text for token in ("高中", "high school", "中专")):
            return 1
        return 0

    @staticmethod
    def _parse_salary_range_monthly_k(raw_value: str | None) -> tuple[float | None, float | None]:
        text = str(raw_value or "").strip().lower()
        if not text:
            return None, None
        if any(token in text for token in ("面议", "negotiable", "open")):
            return None, None

        num_matches = re.findall(r"\d+(?:\.\d+)?", text)
        if not num_matches:
            return None, None
        values = [float(item) for item in num_matches]
        low = min(values)
        high = max(values)

        # Convert annual "万" offers to monthly K.
        if ("万" in text or "w" in text) and any(token in text for token in ("年", "/y", "year", "annual")):
            low = low * 10.0 / 12.0
            high = high * 10.0 / 12.0
            return low, high

        # Plain 万/w defaults to monthly K in common CN JD format (e.g. 1.5-2.5万/月).
        if "万" in text or "w" in text:
            low = low * 10.0
            high = high * 10.0
            return low, high

        # K-based monthly salary.
        if "k" in text:
            return low, high

        # Heuristic fallback for pure numeric ranges.
        if high >= 150.0:
            # likely annual K -> monthly K
            return low / 12.0, high / 12.0
        return low, high

    def _evaluate_compensation_fit(
        self,
        *,
        candidate: Candidate | None,
        job: Job | None,
        resume_evaluation: CandidateJobEvaluation,
        interview_assessment: AIInterviewAssessment,
        composite_score: float,
    ) -> dict[str, Any]:
        candidate_expected = str((candidate.expected_salary if candidate is not None else "") or "").strip()
        job_salary = str((job.salary_range if job is not None else "") or "").strip()
        cand_low, cand_high = self._parse_salary_range_monthly_k(candidate_expected)
        job_low, job_high = self._parse_salary_range_monthly_k(job_salary)

        education_score = _to_float(
            (resume_evaluation.dimension_scores or {}).get("education_match"),
            default=60.0,
        )
        interview_score = _to_float(interview_assessment.total_score, default=0.0)
        resume_score = _to_float(resume_evaluation.final_score, default=0.0)
        capability_score = _clip(0.55 * interview_score + 0.35 * resume_score + 0.10 * education_score, 0.0, 100.0)

        reasons: list[str] = []
        score = 60.0
        if job_low is not None and job_high is not None and cand_low is not None and cand_high is not None:
            overlap_low = max(job_low, cand_low)
            overlap_high = min(job_high, cand_high)
            if overlap_low <= overlap_high:
                score = 86.0
                reasons.append("salary_band_overlap")
            elif cand_low > job_high:
                gap = cand_low - job_high
                score = _clip(76.0 - gap * 6.0, 20.0, 76.0)
                reasons.append("candidate_expected_above_job_band")
            elif cand_high < job_low:
                score = 74.0
                reasons.append("candidate_expected_below_job_band")
        elif job_low is not None and job_high is not None:
            score = 64.0
            reasons.append("candidate_expected_salary_missing")
        else:
            score = 60.0
            reasons.append("job_salary_band_missing")

        score = _clip(score * 0.65 + capability_score * 0.35, 0.0, 100.0)
        if cand_low is not None and job_high is not None and cand_low > job_high and capability_score < 72.0:
            score = _clip(score - 8.0, 0.0, 100.0)
            reasons.append("salary_gap_not_supported_by_capability")
        if composite_score >= 86.0 and score < 78.0:
            score = _clip(score + 6.0, 0.0, 100.0)
            reasons.append("high_composite_offsets_salary_gap")

        candidate_degree = str((candidate.degree if candidate is not None else "") or "").strip()
        job_min_degree = str((job.min_degree if job is not None else "") or "").strip()
        candidate_degree_rank = self._normalize_degree_rank(candidate_degree)
        job_degree_rank = self._normalize_degree_rank(job_min_degree)
        degree_ok = job_degree_rank == 0 or candidate_degree_rank >= job_degree_rank
        if not degree_ok:
            score = _clip(score - 6.0, 0.0, 100.0)
            reasons.append("degree_below_job_min_requirement")

        if score >= 78.0:
            decision = "match"
        elif score >= 62.0:
            decision = "conditional_match"
        else:
            decision = "not_match"

        return {
            "decision": decision,
            "score": round(score, 2),
            "reasons": reasons,
            "candidate_expected_salary": candidate_expected or None,
            "job_salary_range": job_salary or None,
            "candidate_salary_band_k": [round(cand_low, 2), round(cand_high, 2)] if cand_low is not None and cand_high is not None else None,
            "job_salary_band_k": [round(job_low, 2), round(job_high, 2)] if job_low is not None and job_high is not None else None,
            "capability_score": round(capability_score, 2),
            "education_check": {
                "candidate_degree": candidate_degree or None,
                "job_min_degree": job_min_degree or None,
                "matched": bool(degree_ok),
            },
        }

    def decide_composite_assessment(
        self,
        *,
        composite_assessment_id: str,
        payload: CompositeDecisionRequest,
    ) -> CompositeDecisionResponse:
        assessment = self._session.get(CandidateCompositeAssessment, composite_assessment_id)
        if assessment is None:
            raise ResourceNotFoundError(f"Composite assessment '{composite_assessment_id}' was not found")
        pipeline = self._session.get(CandidateJobPipeline, assessment.pipeline_id)
        if pipeline is None:
            raise ResourceNotFoundError(f"Pipeline '{assessment.pipeline_id}' was not found")

        policy = self._resolve_policy(payload.policy_code, payload.policy_version)
        payload_snapshot = dict(assessment.payload or {})
        coverage_rate = _to_float(payload_snapshot.get("coverage_rate"), 0.0)
        interview_confidence = _to_float(payload_snapshot.get("interview_confidence"), 0.0)
        recommendation, _hard_reject, _must_review, reasons = self._decide_by_rules(
            composite_score=_to_float(assessment.final_score),
            composite_confidence=_to_float(assessment.confidence_score) / 100.0,
            risk_tags=[str(item) for item in list(assessment.risk_flags_json or [])],
            critical_min_score=None,
            coverage_rate=coverage_rate,
            interview_confidence=interview_confidence,
        )
        next_step = self._decision_to_next_step(recommendation)

        if payload.dry_run:
            return CompositeDecisionResponse(
                decision=recommendation,
                reason_codes=reasons,
                composite_confidence=round(_to_float(assessment.confidence_score) / 100.0, 4),
                next_step_status=next_step,
            )

        now = _now()
        assessment.recommendation = recommendation
        assessment.status = "decided"
        assessment.policy_version_id = policy.id

        pipeline.next_step_status = next_step
        pipeline.composite_assessment_status = "decision_made"
        pipeline.latest_policy_version_id = policy.id
        pipeline.latest_decision_at = now

        decision_event = DecisionEvent(
            pipeline_id=pipeline.id,
            composite_assessment_id=assessment.id,
            policy_version_id=policy.id,
            event_type="decision_made",
            from_step="composite_computed",
            to_step=next_step,
            decision=recommendation,
            reason_code=reasons[0] if reasons else None,
            reason_text=";".join(reasons) if reasons else None,
            actor_type="system",
            actor_id="assessment_engine",
            trace_id=str(uuid.uuid4()),
            payload={
                "score": _to_float(assessment.final_score),
                "confidence": _to_float(assessment.confidence_score) / 100.0,
                "reason_codes": reasons,
            },
        )
        self._session.add(decision_event)
        if recommendation == "manual_review":
            self._create_review_task(
                pipeline_id=pipeline.id,
                composite_assessment_id=assessment.id,
                reason_codes=reasons,
                risk_tags=[str(item) for item in list(assessment.risk_flags_json or [])],
            )

        self._emit_async_event(
            event_type="decision.made",
            entity_type="candidate_composite_assessment",
            entity_id=assessment.id,
            session_id=None,
            job_id=assessment.job_id,
            payload={
                "pipeline_id": pipeline.id,
                "decision": recommendation,
                "reason_codes": reasons,
                "next_step_status": next_step,
            },
        )
        self._session.commit()
        return CompositeDecisionResponse(
            decision=recommendation,
            reason_codes=reasons,
            composite_confidence=round(_to_float(assessment.confidence_score) / 100.0, 4),
            next_step_status=next_step,
        )

    def override_decision(
        self,
        *,
        composite_assessment_id: str,
        payload: CompositeOverrideRequest,
    ) -> CompositeOverrideResponse:
        assessment = self._session.get(CandidateCompositeAssessment, composite_assessment_id)
        if assessment is None:
            raise ResourceNotFoundError(f"Composite assessment '{composite_assessment_id}' was not found")
        pipeline = self._session.get(CandidateJobPipeline, assessment.pipeline_id)
        if pipeline is None:
            raise ResourceNotFoundError(f"Pipeline '{assessment.pipeline_id}' was not found")

        now = _now()
        next_step = self._decision_to_next_step(payload.decision)
        assessment.recommendation = payload.decision
        assessment.status = "decided"
        pipeline.next_step_status = next_step
        pipeline.composite_assessment_status = "decision_made"
        pipeline.latest_decision_at = now

        self._session.add(
            DecisionEvent(
                pipeline_id=pipeline.id,
                composite_assessment_id=assessment.id,
                policy_version_id=assessment.policy_version_id,
                event_type="decision_overridden",
                from_step="decision_made",
                to_step=next_step,
                decision=payload.decision,
                reason_code=payload.reason_code,
                reason_text=payload.note,
                actor_type="human",
                actor_id=payload.operator_id,
                trace_id=str(uuid.uuid4()),
                payload={"human_override": True},
            )
        )

        if payload.decision == "manual_review":
            self._create_review_task(
                pipeline_id=pipeline.id,
                composite_assessment_id=assessment.id,
                reason_codes=[payload.reason_code],
                risk_tags=[str(item) for item in list(assessment.risk_flags_json or [])],
            )

        self._emit_async_event(
            event_type="decision.overridden",
            entity_type="candidate_composite_assessment",
            entity_id=assessment.id,
            session_id=None,
            job_id=assessment.job_id,
            payload={
                "pipeline_id": pipeline.id,
                "decision": payload.decision,
                "operator_id": payload.operator_id,
                "reason_code": payload.reason_code,
            },
        )
        self._session.commit()
        return CompositeOverrideResponse(
            decision=payload.decision,
            human_override=True,
            override_by=payload.operator_id,
            updated_pipeline_status=next_step,
        )

    def list_review_queue_tasks(
        self,
        *,
        status: str | None,
        priority: int | None,
        assignee: str | None,
        job_id: str | None,
    ) -> ReviewQueueTaskListResponse:
        stmt = select(ReviewQueueTask, CandidateJobPipeline).join(
            CandidateJobPipeline, CandidateJobPipeline.id == ReviewQueueTask.pipeline_id
        )
        if status:
            stmt = stmt.where(ReviewQueueTask.status == status)
        if priority is not None:
            stmt = stmt.where(ReviewQueueTask.priority <= int(priority))
        if assignee:
            stmt = stmt.where(ReviewQueueTask.assignee_id == assignee)
        if job_id:
            stmt = stmt.where(CandidateJobPipeline.job_id == job_id)
        stmt = stmt.order_by(
            ReviewQueueTask.priority.asc(),
            ReviewQueueTask.sla_due_at.asc().nulls_last(),
            ReviewQueueTask.created_at.asc(),
        )
        now = _now()
        rows = list(self._session.execute(stmt.limit(300)).all())
        items = [
            ReviewQueueTaskItem(
                id=task.id,
                pipeline_id=task.pipeline_id,
                candidate_id=pipeline.candidate_id,
                job_id=pipeline.job_id,
                priority=int(task.priority),
                status=task.status,
                assignee_id=task.assignee_id,
                queue_type=task.queue_type,
                sla_due_at=task.sla_due_at,
                age_minutes=_compute_age_minutes(task.created_at, now),
            )
            for task, pipeline in rows
        ]
        return ReviewQueueTaskListResponse(total=len(items), items=items)

    def publish_next_step(
        self,
        *,
        pipeline_id: str,
        assessment_id: str,
        expected_version: str,
    ) -> tuple[str, datetime]:
        pipeline = self._session.get(CandidateJobPipeline, pipeline_id)
        if pipeline is None:
            raise ResourceNotFoundError(f"Pipeline '{pipeline_id}' was not found")
        assessment = self._session.get(CandidateCompositeAssessment, assessment_id)
        if assessment is None:
            raise ResourceNotFoundError(f"Composite assessment '{assessment_id}' was not found")
        if assessment.pipeline_id != pipeline.id:
            raise InvalidStateError("assessment_id does not belong to pipeline_id")
        if str(assessment.composite_version) != str(expected_version):
            raise InvalidStateError(
                f"Composite version mismatch: expected '{expected_version}', actual '{assessment.composite_version}'"
            )

        next_step = pipeline.next_step_status
        if next_step == "pending_decision":
            next_step = self._decision_to_next_step(assessment.recommendation)
            pipeline.next_step_status = next_step

        if next_step == "invited" and pipeline.invitation_status == "not_invited":
            pipeline.invitation_status = "pending"
        pipeline.composite_assessment_status = "published"
        published_at = _now()
        pipeline.latest_decision_at = published_at
        assessment.status = "published"

        self._session.add(
            DecisionEvent(
                pipeline_id=pipeline.id,
                composite_assessment_id=assessment.id,
                policy_version_id=assessment.policy_version_id,
                event_type="decision_published",
                from_step="decision_made",
                to_step=next_step,
                decision=assessment.recommendation,
                reason_code=None,
                reason_text="Pipeline next step published.",
                actor_type="system",
                actor_id="assessment_engine",
                trace_id=str(uuid.uuid4()),
                payload={"expected_version": expected_version},
            )
        )
        self._session.commit()
        return next_step, published_at

    def _ensure_session_exists(self, session_id: str) -> AIInterviewSession:
        entity = self._session.get(AIInterviewSession, session_id)
        if entity is None:
            raise ResourceNotFoundError(f"AI interview session '{session_id}' was not found")
        return entity

    def _backfill_question_answer_records(self, *, session_id: str) -> None:
        existing_count = int(
            self._session.execute(
                select(func.count(AIInterviewQuestionAttempt.id)).where(
                    AIInterviewQuestionAttempt.session_id == session_id
                )
            ).scalar_one()
            or 0
        )
        if existing_count > 0:
            return

        turns = list(
            self._session.execute(
                select(AIInterviewTurn)
                .where(AIInterviewTurn.session_id == session_id)
                .order_by(AIInterviewTurn.turn_no.asc(), AIInterviewTurn.created_at.asc())
            ).scalars().all()
        )
        for turn in turns:
            merged_payload = dict(turn.payload or {})
            if turn.question_id:
                merged_payload.setdefault("question_id", turn.question_id)
            if turn.question_seq is not None:
                merged_payload.setdefault("question_seq", turn.question_seq)
            self.bind_question_answer_from_turn(
                session_id=session_id,
                turn=turn,
                request_payload=merged_payload,
                interview_stage=str(merged_payload.get("interview_stage") or ""),
                commit=False,
            )
        self._session.flush()

    def _get_latest_interview_assessment(self, *, session_id: str) -> AIInterviewAssessment | None:
        return self._session.execute(
            select(AIInterviewAssessment)
            .where(AIInterviewAssessment.session_id == session_id)
            .order_by(desc(AIInterviewAssessment.evaluated_at), desc(AIInterviewAssessment.created_at))
            .limit(1)
        ).scalars().first()

    def _sync_pipeline_after_interview_assessment(
        self,
        *,
        session_id: str,
        assessment: AIInterviewAssessment,
    ) -> None:
        session_entity = self._ensure_session_exists(session_id)
        pipeline = self._session.execute(
            select(CandidateJobPipeline).where(
                CandidateJobPipeline.candidate_id == session_entity.candidate_id,
                CandidateJobPipeline.job_id == session_entity.job_id,
            )
        ).scalars().first()
        if pipeline is None:
            return
        pipeline.interview_status = "interview_completed"
        pipeline.latest_interview_assessment_id = assessment.id
        pipeline.last_interview_evaluated_at = assessment.evaluated_at
        if pipeline.composite_assessment_status in {"", None, "pending"}:
            pipeline.composite_assessment_status = "pending"
        self._session.flush()

    def _score_answer(self, *, attempt: AIInterviewQuestionAttempt, answer: AIInterviewAnswerRecord) -> _AnswerScorePack:
        answer_text = str(answer.answer_text or "").strip()
        question_text = str(attempt.question_text or "").strip()
        lowered = answer_text.lower()
        tokens = [token for token in re.split(r"\s+", lowered) if token]
        unique_token_ratio = (len(set(tokens)) / len(tokens)) if tokens else 0.0
        sentence_count = max(1, len(re.findall(r"[。！？!?\.]+", answer_text)) or 1)
        char_len = len(answer_text)

        evidence_hits = 0
        evidence_hits += len(re.findall(r"\d+", answer_text))
        evidence_hits += len(re.findall(r"(because|therefore|for example|例如|比如|因此|结果)", lowered))
        evidence_density = _clip(evidence_hits / max(1.0, sentence_count + 1), 0.0, 1.0)

        completeness = _clip(25.0 + (char_len / 7.0) + (sentence_count * 8.0), 0.0, 100.0)
        depth = _clip(20.0 + unique_token_ratio * 65.0 + sentence_count * 6.0, 0.0, 100.0)
        evidence = _clip(18.0 + evidence_hits * 10.0 + evidence_density * 30.0, 0.0, 100.0)
        logic_hits = len(re.findall(r"(first|then|finally|because|therefore|首先|然后|最后|因为|所以|因此)", lowered))
        logic = _clip(22.0 + logic_hits * 14.0 + sentence_count * 4.0, 0.0, 100.0)
        asr_confidence = _clip(_to_float(answer.asr_confidence, 0.88), 0.0, 1.0)
        communication = _clip(32.0 + asr_confidence * 36.0 + min(28.0, char_len / 18.0), 0.0, 100.0)

        question_terms = {item for item in re.findall(r"[a-zA-Z0-9_]+", question_text.lower()) if len(item) >= 3}
        answer_terms = {item for item in re.findall(r"[a-zA-Z0-9_]+", lowered) if len(item) >= 3}
        overlap = len(question_terms.intersection(answer_terms))
        overlap_base = max(1, len(question_terms))
        domain_fit = _clip(20.0 + (overlap / overlap_base) * 80.0, 0.0, 100.0)

        risk_tags: list[str] = []
        risk_penalty = 0.0
        if re.search(r"(fake|fraud|illegal|伪造|违法|歧视)", lowered):
            risk_tags.append("compliance_block")
            risk_penalty += 20.0
        if asr_confidence < 0.55:
            risk_tags.append("low_asr_confidence")
            risk_penalty += 8.0
        risk_penalty = _clip(risk_penalty, 0.0, 40.0)

        question_score = _clip(
            QUESTION_SCORE_WEIGHTS["completeness"] * completeness
            + QUESTION_SCORE_WEIGHTS["depth"] * depth
            + QUESTION_SCORE_WEIGHTS["evidence"] * evidence
            + QUESTION_SCORE_WEIGHTS["logic"] * logic
            + QUESTION_SCORE_WEIGHTS["communication"] * communication
            + QUESTION_SCORE_WEIGHTS["domain_fit"] * domain_fit
            - risk_penalty,
            0.0,
            100.0,
        )

        model_confidence = _clip(
            1.0 - (statistics.pstdev([completeness, depth, evidence, logic, communication, domain_fit]) / 100.0),
            0.0,
            1.0,
        )
        reliability = _clip(
            0.50 * asr_confidence + 0.30 * model_confidence + 0.20 * evidence_density,
            0.0,
            1.0,
        )

        if self._llm_client is not None:
            session_entity = self._session.get(AIInterviewSession, attempt.session_id)
            jd_text = ""
            if session_entity and session_entity.job_id:
                job = self._session.get(Job, session_entity.job_id)
                if job:
                    jd_text = f"Title: {job.title}\nRequirements: {job.requirements}"

            from .llm.client import InvokeContext
            from .llm.prompts import get_prompt_template
            
            context = InvokeContext(
                task_key="answer_evaluation",
                trace_id=f"eval-{answer.id}-{uuid.uuid4().hex[:8]}",
                prompt=get_prompt_template("answer_evaluation", "v1").render(
                    job_requirements=jd_text or "No specific JD provided",
                    dimension=str((attempt.context_payload or {}).get("dimension") or "General"),
                    stage=str((attempt.context_payload or {}).get("stage") or "Unknown"),
                    question_text=question_text,
                    answer_text=answer_text,
                )
            )
            
            try:
                llm_result = self._llm_client.invoke_json(context)
                data = llm_result.content
                if isinstance(data, dict) and not data.get("error"):
                    completeness = _clip(data.get("completeness", completeness), 0.0, 100.0)
                    logic = _clip(data.get("logic", logic), 0.0, 100.0)
                    evidence_val = data.get("evidence")
                    if evidence_val is not None:
                        evidence = _clip(float(evidence_val), 0.0, 100.0)
                    communication = _clip(data.get("communication", communication), 0.0, 100.0)
                    domain_fit = _clip(data.get("domain_fit", domain_fit), 0.0, 100.0)
                    
                    if data.get("confidence") is not None:
                        model_confidence = _clip(float(data.get("confidence", model_confidence)), 0.0, 1.0)
                        reliability = _clip(0.50 * asr_confidence + 0.50 * model_confidence, 0.0, 1.0)
                    
                    if data.get("risk_tags"):
                        for tag in data.get("risk_tags", []):
                            if tag not in risk_tags:
                                risk_tags.append(str(tag))
                                risk_penalty += 10.0
                    
                    risk_penalty = _clip(risk_penalty, 0.0, 40.0)
                    
                    # Recompute question_score with LLM outputs
                    question_score = _clip(
                        QUESTION_SCORE_WEIGHTS["completeness"] * completeness
                        + QUESTION_SCORE_WEIGHTS["depth"] * depth
                        + QUESTION_SCORE_WEIGHTS["evidence"] * evidence
                        + QUESTION_SCORE_WEIGHTS["logic"] * logic
                        + QUESTION_SCORE_WEIGHTS["communication"] * communication
                        + QUESTION_SCORE_WEIGHTS["domain_fit"] * domain_fit
                        - risk_penalty,
                        0.0,
                        100.0,
                    )
            except Exception:
                pass

        stage_key = str((attempt.context_payload or {}).get("stage") or "").strip().lower()
        stage_weight = DEFAULT_STAGE_WEIGHTS.get(stage_key, 1.0)
        difficulty_weight = DEFAULT_DIFFICULTY_WEIGHTS.get(str(attempt.difficulty_level or "medium").lower(), 1.0)
        critical_multiplier = 1.2 if bool((attempt.context_payload or {}).get("critical")) else 1.0
        question_weight = _clip(stage_weight * difficulty_weight * critical_multiplier, 0.3, 2.5)

        evidence_refs = [
            {
                "question_attempt_id": attempt.id,
                "answer_record_id": answer.id,
                "evidence_density": round(evidence_density, 4),
                "asr_confidence": round(asr_confidence, 4),
            }
        ]
        return _AnswerScorePack(
            question_score=question_score,
            reliability=reliability,
            question_weight=question_weight,
            risk_penalty=risk_penalty,
            model_confidence=model_confidence,
            evidence_density=evidence_density,
            dimensions={
                "completeness": completeness,
                "depth": depth,
                "evidence": evidence,
                "logic": logic,
                "communication": communication,
                "domain_fit": domain_fit,
            },
            risk_tags=risk_tags,
            evidence_refs=evidence_refs,
        )

    def _decide_by_rules(
        self,
        *,
        composite_score: float,
        composite_confidence: float,
        risk_tags: list[str],
        critical_min_score: float | None,
        coverage_rate: float,
        interview_confidence: float,
    ) -> tuple[str, bool, bool, list[str]]:
        reasons: list[str] = []
        risk_set = {item for item in risk_tags if item}
        if risk_set.intersection(REDLINE_RISK_TAGS):
            reasons.append("redline_risk_hit")
            return "reject", True, False, reasons

        if critical_min_score is not None and float(critical_min_score) < 65.0:
            reasons.append("critical_question_below_65")
            return "reject", True, False, reasons

        if coverage_rate < 0.70 or interview_confidence < 0.60:
            reasons.append("coverage_or_interview_confidence_low")
            return "manual_review", False, True, reasons

        if composite_score >= 82.0 and composite_confidence >= 0.72:
            reasons.append("score_confidence_pass")
            return "advance", False, False, reasons
        if composite_score >= 70.0:
            reasons.append("score_in_manual_band")
            return "manual_review", False, True, reasons
        reasons.append("score_below_reject_threshold")
        return "reject", True, False, reasons

    def _decision_to_next_step(self, decision: str) -> str:
        normalized = str(decision or "").strip().lower()
        if normalized == "advance":
            return "invited"
        if normalized == "manual_review":
            return "hold"
        return "rejected"

    def _resolve_resume_evaluation(
        self,
        *,
        candidate_id: str,
        job_id: str,
        resume_evaluation_id: str | None,
    ) -> CandidateJobEvaluation:
        if resume_evaluation_id:
            entity = self._session.get(CandidateJobEvaluation, resume_evaluation_id)
            if entity is None:
                raise ResourceNotFoundError(f"Resume evaluation '{resume_evaluation_id}' was not found")
            return entity

        entity = self._session.execute(
            select(CandidateJobEvaluation)
            .where(
                CandidateJobEvaluation.candidate_id == candidate_id,
                CandidateJobEvaluation.job_id == job_id,
                CandidateJobEvaluation.status == "completed",
            )
            .order_by(
                desc(CandidateJobEvaluation.evaluated_at),
                desc(CandidateJobEvaluation.created_at),
            )
            .limit(1)
        ).scalars().first()
        if entity is None:
            raise InvalidStateError(
                f"No completed resume evaluation found for candidate '{candidate_id}' under job '{job_id}'"
            )
        return entity

    def _resolve_market_signal(
        self,
        *,
        job_id: str,
        market_context: dict[str, Any],
    ) -> tuple[float, float, str | None]:
        region = str(market_context.get("region") or "").strip().lower()
        snapshot_stmt = select(JobMarketSnapshot).where(JobMarketSnapshot.job_id == job_id)
        if region:
            snapshot_stmt = snapshot_stmt.where(
                or_(
                    JobMarketSnapshot.market_scope == region,
                    JobMarketSnapshot.market_scope == "cn",
                )
            )
        snapshot = self._session.execute(
            snapshot_stmt.order_by(desc(JobMarketSnapshot.snapshot_date), desc(JobMarketSnapshot.created_at)).limit(1)
        ).scalars().first()

        if snapshot is None:
            market_score = 60.0
            data_recency_factor = 0.45
            sample_size_factor = 0.50
            source_quality_factor = 0.65
            confidence = _clip(
                0.40 * data_recency_factor + 0.35 * sample_size_factor + 0.25 * source_quality_factor,
                0.0,
                1.0,
            )
            return market_score, confidence, None

        market_score = _clip(_to_float(snapshot.market_score, 60.0), 0.0, 100.0)
        days_old = max(0, (date.today() - snapshot.snapshot_date).days)
        data_recency_factor = _clip(1.0 - (days_old / 90.0), 0.0, 1.0)
        sample_size_factor = _clip(
            0.55 + (_to_float((snapshot.payload or {}).get("sample_size"), 50.0) / 1000.0),
            0.0,
            1.0,
        )
        source = str(snapshot.source or "").strip().lower()
        source_quality_factor = 0.90 if source in {"official", "trusted", "internal"} else 0.65
        confidence = _clip(
            0.40 * data_recency_factor + 0.35 * sample_size_factor + 0.25 * source_quality_factor,
            0.0,
            1.0,
        )
        return market_score, confidence, snapshot.id

    def _resolve_policy(self, policy_code: str, policy_version: str | None) -> DecisionPolicyVersion:
        base_stmt = select(DecisionPolicyVersion).where(DecisionPolicyVersion.policy_code == policy_code)
        if policy_version:
            entity = self._session.execute(
                base_stmt.where(DecisionPolicyVersion.version == policy_version).limit(1)
            ).scalars().first()
            if entity is None:
                raise ResourceNotFoundError(
                    f"Policy '{policy_code}' version '{policy_version}' was not found"
                )
            return entity

        entity = self._session.execute(
            base_stmt.where(DecisionPolicyVersion.is_default.is_(True)).limit(1)
        ).scalars().first()
        if entity is not None:
            return entity

        entity = self._session.execute(
            base_stmt.where(
                and_(
                    DecisionPolicyVersion.status == "active",
                    or_(
                        DecisionPolicyVersion.effective_to.is_(None),
                        DecisionPolicyVersion.effective_to >= _now(),
                    ),
                )
            )
            .order_by(desc(DecisionPolicyVersion.effective_from), desc(DecisionPolicyVersion.created_at))
            .limit(1)
        ).scalars().first()
        if entity is not None:
            return entity

        default_policy = DecisionPolicyVersion(
            policy_code=policy_code,
            version="v1.0.0",
            status="active",
            description="Auto-created default enterprise policy.",
            resume_weight=0.35,
            interview_weight=0.45,
            market_weight=0.15,
            stability_weight=0.05,
            risk_penalty_weight=0.20,
            hard_rules_json={
                "hard_reject_tags": sorted(REDLINE_RISK_TAGS),
                "must_review_tags": ["conflicting_answers", "fabrication_risk"],
            },
            threshold_rules_json={
                "advance_min_score": 82,
                "manual_min_score": 70,
                "advance_min_confidence": 0.72,
            },
            override_rules_json={"allow_force_advance": True},
            formula_text=(
                "composite_score = clip(0,100,0.4*resume + 0.45*interview + 0.15*market - risk_penalty + bonus)"
            ),
            is_default=True,
            effective_from=_now(),
            effective_to=None,
            created_by="system",
            updated_by="system",
        )
        self._session.add(default_policy)
        self._session.flush()
        return default_policy

    def _create_review_task(
        self,
        *,
        pipeline_id: str,
        composite_assessment_id: str,
        reason_codes: list[str],
        risk_tags: list[str],
    ) -> ReviewQueueTask:
        now = _now()
        entity = ReviewQueueTask(
            pipeline_id=pipeline_id,
            composite_assessment_id=composite_assessment_id,
            queue_type="human_review",
            priority=20 if "redline_risk_hit" in reason_codes else 50,
            status="open",
            sla_due_at=now + timedelta(hours=24),
            assignee_id=None,
            claimed_at=None,
            resolved_at=None,
            resolution=None,
            resolution_note=None,
            checklist_json={
                "reason_codes": reason_codes,
                "risk_tags": risk_tags,
                "required_actions": ["verify_evidence", "review_context", "final_signoff"],
            },
            payload={},
        )
        self._session.add(entity)
        self._session.flush()
        self._emit_async_event(
            event_type="review.task.created",
            entity_type="review_queue_task",
            entity_id=entity.id,
            session_id=None,
            payload={"pipeline_id": pipeline_id, "composite_assessment_id": composite_assessment_id},
        )
        return entity

    def _emit_async_event(
        self,
        *,
        event_type: str,
        entity_type: str,
        entity_id: str,
        payload: dict[str, Any],
        session_id: str | None = None,
        job_id: str | None = None,
    ) -> None:
        trace_id = str(uuid.uuid4())
        idempotency_key = f"{event_type}:{entity_id}:{trace_id}"
        envelope = {
            "trace_id": trace_id,
            "idempotency_key": idempotency_key,
            "schema_version": "1.0",
            "occurred_at": _now().isoformat(),
            "producer_service": "enterprise_assessment_service",
            **payload,
        }
        self._event_repository.create(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            status="success",
            operator="system",
            session_id=session_id,
            job_id=job_id,
            payload=envelope,
        )


def get_enterprise_assessment_service(session: Session, llm_client: Any = None) -> EnterpriseAssessmentService:
    """Return an enterprise assessment service bound to current DB session."""
    if llm_client is None:
        try:
            from .llm.client import LLMClient
            from .llm.router import ModelRouter
            llm_client = LLMClient(router=ModelRouter())
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to initialize LLM Client: {e}", exc_info=True)
    return EnterpriseAssessmentService(session, llm_client=llm_client)
