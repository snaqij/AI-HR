"""Detailed candidate evaluation services."""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.exceptions import ConnectorOperationError, InvalidStateError
from ..domain.constants import PromptTaskKey
from ..repositories.ai_observability import AIObservabilityRepository
from ..repositories.ai_runtime import AIRuntimeRepository
from ..repositories.ai_scoring import AIScoringRepository
from ..repositories.candidate_job_evaluations import CandidateJobEvaluationRepository
from ..repositories.candidate_job_pipeline import CandidateJobPipelineRepository
from ..repositories.candidates import CandidateRepository
from ..repositories.job_candidates import JobCandidateRepository
from ..repositories.jobs import JobRepository
from ..repositories.resume_attachments import ResumeAttachmentRepository
from ..repositories.resume_profiles import ResumeProfileRepository
from ..schemas.ai_resume import ResumeAttachmentSyncRequest, ResumeNormalizeRequest, ResumeParseRequest
from ..schemas.candidate_evaluations import (
    CandidateEvaluationDetailResult,
    CandidateEvaluationListItem,
    CandidateEvaluationListResult,
    CandidateEvaluationRequest,
    CandidateEvaluationResponse,
    CandidateEvaluationUpdateRequest,
)
from ..schemas.candidates import CandidateResponse, CandidateSummaryResponse
from .ai_resume import AIResumeService
from .llm.client import InvokeContext, LLMClient
from .llm.guardrails import GuardrailService
from .llm.prompts import PromptTemplate, get_prompt_template
from .llm.router import ModelRouter
from .policy.decision import PolicyDecisionService

logger = logging.getLogger(__name__)

_SKILL_KEYWORDS = (
    "python",
    "fastapi",
    "django",
    "flask",
    "java",
    "spring",
    "springboot",
    "mysql",
    "postgresql",
    "redis",
    "docker",
    "kubernetes",
    "golang",
    "linux",
    "sqlalchemy",
)
_EDUCATION_RANK = {"高中": 1, "中专": 2, "大专": 3, "本科": 4, "硕士": 5, "博士": 6}


@dataclass(slots=True)
class _JobRequirementSignals:
    skills: list[str]
    min_years: float | None
    education_level: str | None


class CandidateEvaluationService:
    """Produces detailed candidate evaluations aligned to job requirements."""

    def __init__(self, session: Session):
        self._session = session
        self._settings = get_settings()
        self._candidate_repository = CandidateRepository(session)
        self._job_repository = JobRepository(session)
        self._job_candidate_repository = JobCandidateRepository(session)
        self._resume_profile_repository = ResumeProfileRepository(session)
        self._resume_attachment_repository = ResumeAttachmentRepository(session)
        self._evaluation_repository = CandidateJobEvaluationRepository(session)
        self._pipeline_repository = CandidateJobPipelineRepository(session)
        self._scoring_repository = AIScoringRepository(session)
        self._policy_service = PolicyDecisionService()
        runtime_repository = AIRuntimeRepository(session)
        self._runtime_repository = runtime_repository
        observability_repository = AIObservabilityRepository(session)
        self._llm_client = LLMClient(
            router=ModelRouter(runtime_repository),
            guardrail_service=GuardrailService(),
            observability_repository=observability_repository,
        )
        self._resume_service = AIResumeService(session)

    def evaluate_candidate(
        self,
        *,
        job_id: str,
        candidate_id: str,
        payload: CandidateEvaluationRequest,
    ) -> CandidateEvaluationDetailResult:
        job = self._job_repository.get(job_id)
        candidate = self._candidate_repository.get(candidate_id)
        job_link = self._job_candidate_repository.get_link(job_id, candidate_id)
        if job_link is None:
            raise InvalidStateError(f"Candidate '{candidate_id}' is not linked to job '{job_id}'")

        pipeline = self._pipeline_repository.ensure(
            candidate_id=candidate_id,
            job_id=job_id,
            source_channel=job_link.channel,
            external_candidate_id=job_link.external_candidate_id,
            payload={"job_candidate_id": job_link.id},
        )

        effective_version = payload.evaluation_version
        existing = self._evaluation_repository.get_by_version(
            candidate_id=candidate_id,
            job_id=job_id,
            evaluation_version=effective_version,
        )
        if existing is not None and not payload.force_refresh:
            return CandidateEvaluationDetailResult(
                candidate=CandidateResponse.model_validate(candidate),
                evaluation=self._to_response(existing),
                pipeline_status=self._pipeline_to_dict(pipeline),
            )
        if existing is not None and payload.force_refresh:
            effective_version = f"{payload.evaluation_version}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"

        latest_attachment = self._resume_attachment_repository.get_latest(candidate_id)
        if latest_attachment is None:
            # Try to fetch attachment on-demand to avoid evaluating on incomplete profile fallback text.
            try:
                self._resume_service.sync_resume_attachment(ResumeAttachmentSyncRequest(candidate_id=candidate_id))
            except ConnectorOperationError as exc:
                # For locally imported candidates (for example source_channel=local_script),
                # no remote connector may exist. If resume_text is already present, continue
                # with local text instead of failing hard.
                if (candidate.resume_text or "").strip():
                    logger.warning(
                        "candidate_evaluation.attachment_sync_skipped candidate_id=%s channel=%s reason=%s",
                        candidate_id,
                        candidate.source_channel,
                        exc,
                    )
                else:
                    raise
            latest_attachment = self._resume_attachment_repository.get_latest(candidate_id)

        # Always prefer latest attachment full text for evaluation accuracy.
        refreshed_from_attachment = self._resume_service.hydrate_resume_text_from_latest_attachment(
            candidate_id,
            force_refresh=True,
        )
        if not refreshed_from_attachment and latest_attachment is not None:
            # Retry once by re-syncing attachment; some channels return stale/partial blobs in first attempt.
            self._resume_service.sync_resume_attachment(ResumeAttachmentSyncRequest(candidate_id=candidate_id))
            refreshed_from_attachment = self._resume_service.hydrate_resume_text_from_latest_attachment(
                candidate_id,
                force_refresh=True,
            )

        # Always re-parse + normalize before evaluation to avoid stale profile fields.
        self._resume_service.parse_resume(ResumeParseRequest(candidate_id=candidate_id))
        self._resume_service.normalize_resume(ResumeNormalizeRequest(candidate_id=candidate_id))
        if refreshed_from_attachment or not (candidate.resume_text or "").strip():
            candidate = self._candidate_repository.get(candidate_id)
        else:
            candidate = self._candidate_repository.get(candidate_id)

        resume_profile = self._ensure_resume_profile(candidate_id)
        attachment = self._resume_attachment_repository.get_latest(candidate_id)
        resume_risks = self._resume_profile_repository.list_risks(candidate_id)
        normalized_profile = dict((resume_profile.normalized_json or {}) if resume_profile else {})
        raw_profile = dict(candidate.raw_profile or {})
        resume_text = (candidate.resume_text or (resume_profile.raw_text if resume_profile else "") or "").strip()
        if not resume_text:
            raise InvalidStateError(f"Candidate '{candidate_id}' has no resume text to evaluate")
        if attachment is not None:
            source = str(raw_profile.get("resume_text_source") or "")
            if source not in {"attachment", "attachment_refresh", "attachment_backfill"}:
                raise InvalidStateError(
                    f"Candidate '{candidate_id}' has attachment but resume text is not parsed from attachment body. "
                    "Please re-sync attachment or enable OCR-capable parsing."
                )
            if re.search(r"(?im)^(name|school|degree|work_experience|latest_company|expected_salary)\s*:", resume_text):
                raise InvalidStateError(
                    f"Candidate '{candidate_id}' resume text appears to be metadata fallback, not attachment full text."
                )
        if len(resume_text) < 120:
            raise InvalidStateError(
                f"Candidate '{candidate_id}' resume text extracted from attachment is too short ({len(resume_text)} chars); "
                "please verify attachment download/parsing before evaluation."
            )

        job_requirements_text = (job.requirements or "").strip()
        if job_requirements_text.lower() == "imported from remote recruiting channel.":
            job_requirements_text = f"岗位名称：{job.title}。该职位要求来自远程渠道，请结合候选人附件简历进行完整评估。"

        requirement_signals = self._extract_job_requirement_signals(job_requirements_text)
        heuristic = self._build_heuristic_evaluation(
            job_title=job.title,
            job_requirements=job_requirements_text,
            requirement_signals=requirement_signals,
            resume_text=resume_text,
            normalized_profile=normalized_profile,
            raw_profile=raw_profile,
            resume_risks=resume_risks,
        )

        if not self._is_llm_enabled():
            raise InvalidStateError(
                "Candidate evaluation is configured as LLM-only. "
                "Please enable runtime feature 'ai_candidate_evaluation_llm' or set AI_HR_AI_CANDIDATE_EVALUATION_LLM_ENABLED=true."
            )
        provider = (self._settings.llm_provider or "").strip().lower()
        if provider == "mock":
            raise InvalidStateError(
                "Candidate evaluation requires a real LLM provider. "
                "Please set AI_HR_LLM_PROVIDER to a non-mock provider (for example 'openai') and configure API key."
            )
        llm_output = self._evaluate_with_llm(
            candidate_id=candidate_id,
            job_title=job.title,
            salary_range=job.salary_range or "面议",
            job_requirements=job_requirements_text,
            resume_text=resume_text,
            normalized_profile=normalized_profile,
            raw_profile=raw_profile,
            resume_risks=resume_risks,
        )
        if llm_output is None:
            raise InvalidStateError("LLM evaluation failed. Please verify LLM provider/model configuration and retry.")

        merged = self._merge_evaluation_outputs(heuristic=heuristic, llm_output=llm_output)
        decision = self._policy_service.decide_score_action(
            confidence=float(merged["confidence_score"] or 0.0),
            risk_tags=list(merged["risk_flags"]),
        )
        merged["risk_flags"] = self._dedupe_strings(list(merged["risk_flags"]) + list(decision.policy_flags))
        merged["recommendation"] = self._resolve_recommendation(
            final_score=float(merged["final_score"]),
            confidence=float(merged["confidence_score"] or 0.0),
            decision_action=decision.action,
            risk_flags=list(merged["risk_flags"]),
            dimension_scores=dict(merged["dimension_scores"]),
            job_requirement_coverage=dict(merged["job_requirement_coverage"]),
        )

        evaluation = self._evaluation_repository.create(
            candidate_id=candidate_id,
            job_id=job_id,
            evaluation_version=effective_version,
            resume_attachment_id=attachment.id if attachment else None,
            source="llm",
            status="completed",
            match_score=float(merged["match_score"]),
            competitiveness_score=float(merged["competitiveness_score"]),
            final_score=float(merged["final_score"]),
            confidence_score=float(merged["confidence_score"]) if merged["confidence_score"] is not None else None,
            recommendation=str(merged["recommendation"]),
            summary=str(merged["summary"]),
            dimension_scores=dict(merged["dimension_scores"]),
            strengths=list(merged["strengths"]),
            weaknesses=list(merged["weaknesses"]),
            highlights=list(merged["highlights"]),
            risk_flags=list(merged["risk_flags"]),
            job_requirement_coverage=dict(merged["job_requirement_coverage"]),
            raw_llm_output=llm_output,
        )
        self._pipeline_repository.mark_evaluated(
            pipeline.id,
            evaluation_id=evaluation.id,
            payload_patch={"latest_final_score": float(merged["final_score"])},
        )
        self._sync_candidate_summary(
            candidate_id=candidate_id,
            final_score=float(merged["final_score"]),
            dimension_scores={k: float(v) for k, v in dict(merged["dimension_scores"]).items()},
            summary=str(merged["summary"]),
        )
        self._scoring_repository.upsert_job_score(
            candidate_id=candidate_id,
            job_id=job_id,
            total_score=float(merged["final_score"]),
            dimension_scores={k: float(v) for k, v in dict(merged["dimension_scores"]).items()},
            explanation=str(merged["summary"]),
            risk_tags=list(merged["risk_flags"]),
            score_version="candidate-evaluation-v1",
        )
        self._session.commit()

        candidate = self._candidate_repository.get(candidate_id)
        pipeline = self._pipeline_repository.get(pipeline.id)
        evaluation = self._evaluation_repository.get(evaluation.id)
        return CandidateEvaluationDetailResult(
            candidate=CandidateResponse.model_validate(candidate),
            evaluation=self._to_response(evaluation),
            pipeline_status=self._pipeline_to_dict(pipeline),
        )

    def list_job_evaluations(
        self,
        *,
        job_id: str,
        limit: int = 100,
        offset: int = 0,
        candidate_ids: list[str] | None = None,
    ) -> CandidateEvaluationListResult:
        self._job_repository.get(job_id)
        entities = self._evaluation_repository.list_by_job(
            job_id,
            limit=limit,
            offset=offset,
            candidate_ids=candidate_ids,
        )
        candidates = self._candidate_repository.list_by_ids(
            [entity.candidate_id for entity in entities],
            summary_only=True,
        )
        candidate_map = {candidate.id: candidate for candidate in candidates}
        items: list[CandidateEvaluationListItem] = []
        for entity in entities:
            candidate = candidate_map.get(entity.candidate_id)
            if candidate is None:
                continue
            items.append(
                CandidateEvaluationListItem(
                    candidate=CandidateSummaryResponse.model_validate(candidate),
                    evaluation=self._to_response(entity),
                )
            )
        return CandidateEvaluationListResult(job_id=job_id, total=len(items), items=items)

    def get_latest_job_candidate_evaluation(self, *, job_id: str, candidate_id: str) -> CandidateEvaluationDetailResult:
        self._job_repository.get(job_id)
        candidate = self._candidate_repository.get(candidate_id)
        job_link = self._job_candidate_repository.get_link(job_id, candidate_id)
        if job_link is None:
            raise InvalidStateError(f"Candidate '{candidate_id}' is not linked to job '{job_id}'")
        pipeline = self._pipeline_repository.get_by_candidate_job(candidate_id=candidate_id, job_id=job_id)
        evaluation = self._evaluation_repository.get_latest_by_candidate_job(candidate_id=candidate_id, job_id=job_id)
        if evaluation is None:
            raise InvalidStateError(f"No evaluation found for candidate '{candidate_id}' under job '{job_id}'")
        return CandidateEvaluationDetailResult(
            candidate=CandidateResponse.model_validate(candidate),
            evaluation=self._to_response(evaluation),
            pipeline_status=self._pipeline_to_dict(pipeline) if pipeline else {},
        )

    def update_latest_job_candidate_evaluation(
        self,
        *,
        job_id: str,
        candidate_id: str,
        payload: CandidateEvaluationUpdateRequest,
    ) -> CandidateEvaluationDetailResult:
        self._job_repository.get(job_id)
        candidate = self._candidate_repository.get(candidate_id)
        job_link = self._job_candidate_repository.get_link(job_id, candidate_id)
        if job_link is None:
            raise InvalidStateError(f"Candidate '{candidate_id}' is not linked to job '{job_id}'")
        evaluation = self._evaluation_repository.get_latest_by_candidate_job(candidate_id=candidate_id, job_id=job_id)
        if evaluation is None:
            raise InvalidStateError(f"No evaluation found for candidate '{candidate_id}' under job '{job_id}'")

        updated = self._evaluation_repository.update(
            evaluation.id,
            recommendation=payload.recommendation,
            summary=payload.summary,
            strengths=self._sanitize_string_list(payload.strengths),
            weaknesses=self._sanitize_string_list(payload.weaknesses),
            highlights=self._sanitize_string_list(payload.highlights),
            risk_flags=self._sanitize_string_list(payload.risk_flags),
            reviewed_by=payload.reviewed_by,
        )
        self._session.commit()
        refreshed = self._evaluation_repository.get(updated.id)
        pipeline = self._pipeline_repository.get_by_candidate_job(candidate_id=candidate_id, job_id=job_id)
        return CandidateEvaluationDetailResult(
            candidate=CandidateResponse.model_validate(candidate),
            evaluation=self._to_response(refreshed),
            pipeline_status=self._pipeline_to_dict(pipeline) if pipeline else {},
        )

    def _ensure_resume_profile(self, candidate_id: str):
        profile = self._resume_profile_repository.get_profile(candidate_id)
        if profile is not None:
            return profile
        self._resume_service.normalize_resume(ResumeNormalizeRequest(candidate_id=candidate_id))
        return self._resume_profile_repository.get_profile(candidate_id)

    def _extract_job_requirement_signals(self, requirements: str) -> _JobRequirementSignals:
        lower = (requirements or "").lower()
        skills = sorted({keyword for keyword in _SKILL_KEYWORDS if keyword in lower})
        years_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:年|years?)", requirements or "", re.IGNORECASE)
        min_years = float(years_match.group(1)) if years_match else None
        education_level = None
        for level in ("博士", "硕士", "本科", "大专"):
            if level in requirements:
                education_level = level
                break
        return _JobRequirementSignals(skills=skills, min_years=min_years, education_level=education_level)

    def _build_heuristic_evaluation(
        self,
        *,
        job_title: str,
        job_requirements: str,
        requirement_signals: _JobRequirementSignals,
        resume_text: str,
        normalized_profile: dict[str, Any],
        raw_profile: dict[str, Any],
        resume_risks: list[Any],
    ) -> dict[str, Any]:
        candidate_skills = {str(item).strip().lower() for item in normalized_profile.get("skills", []) if str(item).strip()}
        required_skills = set(requirement_signals.skills)
        matched_skills = sorted(candidate_skills & required_skills)
        job_requirement_coverage = {skill: ("matched" if skill in matched_skills else "missing") for skill in sorted(required_skills)}
        lower_requirements = (job_requirements or "").lower()

        skill_match = 72.0 if not required_skills and candidate_skills else 45.0
        if required_skills:
            skill_match = 40.0 + 60.0 * (len(matched_skills) / max(1, len(required_skills)))

        candidate_years = self._safe_float(normalized_profile.get("experience_years"))
        experience_match = 70.0
        if requirement_signals.min_years is not None:
            if candidate_years is None:
                experience_match = 45.0
            elif candidate_years >= requirement_signals.min_years:
                experience_match = min(100.0, 80.0 + (candidate_years - requirement_signals.min_years) * 5.0)
            else:
                ratio = max(0.0, candidate_years / max(requirement_signals.min_years, 0.1))
                experience_match = 35.0 + 45.0 * ratio
        elif candidate_years is not None:
            experience_match = min(92.0, 60.0 + candidate_years * 5.0)

        candidate_education = str(normalized_profile.get("education_level") or "").strip()
        education_match = self._calculate_education_score(candidate_education, requirement_signals.education_level)

        projects = normalized_profile.get("projects") if isinstance(normalized_profile.get("projects"), list) else []
        project_relevance = self._calculate_project_relevance(
            projects=projects,
            resume_text=resume_text,
            matched_skills=matched_skills,
            job_requirements=job_requirements,
        )
        internship_score, internship_count = self._calculate_internship_score(resume_text=resume_text, raw_profile=raw_profile)
        contest_score, contest_count = self._calculate_contest_score(resume_text=resume_text, raw_profile=raw_profile)
        academic_score, gpa_value = self._calculate_academic_score(
            resume_text=resume_text,
            normalized_profile=normalized_profile,
            raw_profile=raw_profile,
        )

        stability_score = self._calculate_stability_score(raw_profile=raw_profile, resume_risks=resume_risks)
        resume_completeness = self._calculate_resume_completeness(
            resume_text=resume_text,
            normalized_profile=normalized_profile,
        )
        jd_coverage = 70.0 if not required_skills else 100.0 * (len(matched_skills) / max(1, len(required_skills)))

        match_score = round(
            skill_match * 0.28
            + experience_match * 0.16
            + education_match * 0.10
            + project_relevance * 0.16
            + internship_score * 0.10
            + contest_score * 0.06
            + academic_score * 0.06
            + jd_coverage * 0.08,
            2,
        )
        competitiveness_score = round(
            project_relevance * 0.24
            + stability_score * 0.20
            + resume_completeness * 0.16
            + experience_match * 0.16
            + internship_score * 0.10
            + contest_score * 0.07
            + academic_score * 0.07,
            2,
        )
        learning_agility = self._calculate_learning_agility(
            internship_score=internship_score,
            contest_score=contest_score,
            academic_score=academic_score,
            project_relevance=project_relevance,
            resume_completeness=resume_completeness,
            candidate_years=candidate_years,
            requirement_signals=requirement_signals,
        )
        engineering_ability = self._calculate_engineering_ability(
            skill_match=skill_match,
            experience_match=experience_match,
            project_relevance=project_relevance,
            stability_score=stability_score,
            jd_coverage=jd_coverage,
        )
        final_score = round(
            match_score * 0.45 + competitiveness_score * 0.15 + learning_agility * 0.20 + engineering_ability * 0.20,
            2,
        )
        requirement_strictness = self._estimate_requirement_strictness(
            required_skills=required_skills,
            min_years=requirement_signals.min_years,
            education_level=requirement_signals.education_level,
            requirement_text=job_requirements,
        )
        evidence_quality = self._estimate_evidence_quality(
            resume_text=resume_text,
            projects=projects,
            internship_count=internship_count,
            contest_count=contest_count,
            gpa_value=gpa_value,
            matched_skills=matched_skills,
            required_skills=required_skills,
        )
        confidence_score = round(
            min(
                0.92,
                0.45
                + (0.12 if candidate_skills else 0.0)
                + (0.12 if candidate_years is not None else 0.0)
                + (0.10 if candidate_education else 0.0)
                + (0.08 if projects else 0.0)
                + (0.05 if internship_count > 0 else 0.0)
                + (0.05 if len(resume_text) >= 80 else 0.0),
            ),
            2,
        )
        risk_flags = [str(risk.risk_code) for risk in resume_risks]
        if skill_match < 60:
            risk_flags.append("skill_match_low")
        if project_relevance < 60:
            risk_flags.append("project_evidence_weak")
        if internship_score < 55:
            risk_flags.append("internship_evidence_weak")
        if contest_score < 50 and ("contest" in lower_requirements or "竞赛" in job_requirements):
            risk_flags.append("contest_evidence_weak")
        if academic_score < 55 and ("gpa" in lower_requirements or "成绩" in job_requirements):
            risk_flags.append("academic_performance_weak")
        if resume_completeness < 65:
            risk_flags.append("resume_completeness_low")
        if learning_agility < 60:
            risk_flags.append("learning_agility_low")
        if engineering_ability < 60:
            risk_flags.append("engineering_ability_low")
        risk_penalty = self._estimate_risk_penalty(
            risk_flags=risk_flags,
            resume_risks=resume_risks,
            jd_coverage=jd_coverage,
            requirement_strictness=requirement_strictness,
        )
        final_score = self._calibrate_final_score(
            base_final=final_score,
            jd_coverage=jd_coverage,
            requirement_strictness=requirement_strictness,
            evidence_quality=evidence_quality,
            risk_penalty=risk_penalty,
        )

        strengths: list[str] = []
        if matched_skills:
            strengths.append(f"核心技能匹配度高：{', '.join(matched_skills[:4])}")
        if experience_match >= 80:
            strengths.append("工作经验深度能够覆盖当前岗位要求")
        if project_relevance >= 80:
            strengths.append("项目经历与目标岗位场景高度相关")
        if internship_count > 0 and internship_score >= 70:
            strengths.append("实习经历具备可验证的交付证据")
        if contest_count > 0 and contest_score >= 65:
            strengths.append("竞赛/获奖经历体现出较强主动性与竞争力")
        if academic_score >= 75:
            strengths.append("学业表现整体较好")

        weaknesses: list[str] = []
        if not matched_skills and required_skills:
            weaknesses.append("关键岗位技能缺少直接证据支撑")
        if stability_score < 65:
            weaknesses.append("职业稳定性存在不确定性，需要面试进一步核验")
        if project_relevance < 60:
            weaknesses.append("项目经历与目标业务场景相关性不足")
        if internship_score < 55:
            weaknesses.append("实习经历证据不足，或缺少可量化成果")
        if contest_score < 50 and ("contest" in lower_requirements or "竞赛" in job_requirements):
            weaknesses.append("竞赛相关证据弱于岗位偏好")
        if academic_score < 55 and ("gpa" in lower_requirements or "成绩" in job_requirements):
            weaknesses.append("学业表现证据低于岗位期望")

        highlights = self._dedupe_strings(
            [job_title, *(f"匹配技能：{skill}" for skill in matched_skills[:3]), f"最终得分：{final_score:.1f}"]
        )
        summary = self._build_summary(
            final_score=final_score,
            match_score=match_score,
            competitiveness_score=competitiveness_score,
            matched_skills=matched_skills,
            weaknesses=weaknesses,
        )

        job_requirement_coverage.update(
            {
                "education_requirement": "matched" if education_match >= 70 else "partial" if candidate_education else "missing",
                "internship_signal": "matched" if internship_score >= 70 else "partial" if internship_count > 0 else "missing",
                "project_signal": "matched" if project_relevance >= 70 else "partial" if projects else "missing",
                "contest_signal": "matched" if contest_score >= 65 else "partial" if contest_count > 0 else "missing",
                "grade_signal": "matched" if academic_score >= 70 else "partial" if gpa_value is not None else "missing",
            }
        )

        return {
            "match_score": match_score,
            "competitiveness_score": competitiveness_score,
            "final_score": final_score,
            "confidence_score": confidence_score,
            "dimension_scores": {
                "skill_match": round(skill_match, 2),
                "experience_match": round(experience_match, 2),
                "education_match": round(education_match, 2),
                "project_relevance": round(project_relevance, 2),
                "internship_score": round(internship_score, 2),
                "contest_score": round(contest_score, 2),
                "academic_score": round(academic_score, 2),
                "stability_score": round(stability_score, 2),
                "resume_completeness": round(resume_completeness, 2),
                "jd_coverage": round(jd_coverage, 2),
                "learning_agility": round(learning_agility, 2),
                "engineering_ability": round(engineering_ability, 2),
                "requirement_strictness": round(requirement_strictness, 2),
                "evidence_quality": round(evidence_quality, 2),
                "risk_penalty": round(risk_penalty, 2),
            },
            "strengths": strengths,
            "weaknesses": weaknesses,
            "highlights": highlights,
            "risk_flags": self._dedupe_strings(risk_flags),
            "recommendation": "review",
            "summary": summary,
            "job_requirement_coverage": job_requirement_coverage,
        }

    def _evaluate_with_llm(
        self,
        *,
        candidate_id: str,
        job_title: str,
        salary_range: str,
        job_requirements: str,
        resume_text: str,
        normalized_profile: dict[str, Any],
        raw_profile: dict[str, Any],
        resume_risks: list[Any],
    ) -> dict[str, Any] | None:
        active_prompt = self._runtime_repository.get_active_prompt(PromptTaskKey.CANDIDATE_EVALUATION)
        if active_prompt is not None:
            template = PromptTemplate(
                task_key=PromptTaskKey.CANDIDATE_EVALUATION,
                version=active_prompt.version,
                system_prompt=active_prompt.system_prompt,
                user_template=active_prompt.user_template,
            )
        else:
            template = get_prompt_template(PromptTaskKey.CANDIDATE_EVALUATION, "v1")
        compact_profile = self._compact_raw_profile_for_llm(raw_profile)
        requirement_signals = self._extract_job_requirement_signals(job_requirements)
        strict_directive = self._build_candidate_matching_directive(
            requirement_signals=requirement_signals,
            resume_risk_count=len(resume_risks),
        )
        render_payload = dict(
            job_title=job_title,
            salary_range=salary_range,
            job_requirements=job_requirements,
            resume_text=resume_text,
            normalized_profile=normalized_profile,
            raw_profile=compact_profile,
            resume_risks=[
                {"risk_code": str(item.risk_code), "risk_level": str(item.risk_level), "detail": str(item.detail)}
                for item in resume_risks
            ],
        )
        try:
            user_prompt = template.render(**render_payload)
        except KeyError:
            # Runtime prompt template may miss required placeholders; fallback to built-in safe template.
            fallback = get_prompt_template(PromptTaskKey.CANDIDATE_EVALUATION, "v1")
            user_prompt = fallback.render(**render_payload)

        prompt = "\n".join([user_prompt, strict_directive])
        header = (
            f"[AI-HR][candidate_evaluation] prompt(candidate_id={candidate_id}, version={template.version}, chars={len(prompt)})\n"
            f"{'-' * 32}\n"
        )
        trailer = f"\n{'-' * 32}"
        try:
            logger.debug("%s%s%s", header, prompt, trailer)
        except UnicodeEncodeError:
            escaped_prompt = prompt.encode("unicode_escape", errors="replace").decode("ascii", errors="ignore")
            logger.debug("%s%s%s", header, escaped_prompt, trailer)
        result = self._llm_client.invoke_json(
            InvokeContext(
                task_key=PromptTaskKey.CANDIDATE_EVALUATION,
                trace_id=str(uuid.uuid4()),
                prompt=prompt,
                system_prompt=template.system_prompt,
                entity_type="candidate",
                entity_id=candidate_id,
            )
        )
        if result.fallback_used or result.content.get("error"):
            return None
        return dict(result.content)

    def _compact_raw_profile_for_llm(self, raw_profile: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(raw_profile, dict):
            return {}
        preferred_keys = (
            "name",
            "city",
            "school",
            "major",
            "year",
            "position",
            "positionStatus",
            "salaryDesc",
            "email",
            "labels",
            "workExpList",
            "eduExpList",
            "projectExperience",
            "skills",
            "skillList",
            "selfDescription",
            "advantage",
            "resume_attachment_file_name",
            "resume_text_source",
        )
        compact: dict[str, Any] = {}
        for key in preferred_keys:
            if key not in raw_profile:
                continue
            value = raw_profile.get(key)
            if value in (None, "", [], {}):
                continue
            if isinstance(value, str):
                compact[key] = value[:500]
                continue
            if isinstance(value, list):
                compact[key] = value[:8]
                continue
            if isinstance(value, dict):
                compact[key] = dict(list(value.items())[:12])
                continue
            compact[key] = value
        return compact

    def _merge_evaluation_outputs(self, *, heuristic: dict[str, Any], llm_output: dict[str, Any]) -> dict[str, Any]:
        merged_dimensions: dict[str, float] = {}
        for key, value in dict(llm_output.get("dimension_scores") or {}).items():
            if not isinstance(value, (int, float)):
                continue
            merged_dimensions[str(key)] = round(max(0.0, min(float(value), 100.0)), 2)
        # Keep deterministic heuristic-only dimensions as supplementary signals.
        for key in (
            "jd_coverage",
            "learning_agility",
            "engineering_ability",
            "requirement_strictness",
            "evidence_quality",
            "risk_penalty",
        ):
            if key in merged_dimensions:
                continue
            value = heuristic.get("dimension_scores", {}).get(key)
            if isinstance(value, (int, float)):
                merged_dimensions[key] = round(float(value), 2)

        match_score = round(
            max(0.0, min(float(llm_output.get("match_score", heuristic["match_score"])), 100.0)),
            2,
        )
        competitiveness_score = round(
            max(0.0, min(float(llm_output.get("competitiveness_score", heuristic["competitiveness_score"])), 100.0)),
            2,
        )
        final_score = round(
            max(0.0, min(float(llm_output.get("final_score", heuristic["final_score"])), 100.0)),
            2,
        )
        confidence_score = round(
            max(0.0, min(float(llm_output.get("confidence_score", heuristic["confidence_score"])), 1.0)),
            2,
        )
        coverage = {
            **dict(heuristic["job_requirement_coverage"]),
            **dict(llm_output.get("job_requirement_coverage") or {}),
        }
        learning_agility = self._extract_dimension_score(
            merged_dimensions=merged_dimensions,
            heuristic=heuristic,
            key="learning_agility",
        )
        engineering_ability = self._extract_dimension_score(
            merged_dimensions=merged_dimensions,
            heuristic=heuristic,
            key="engineering_ability",
        )
        skill_coverage_ratio = self._coverage_to_ratio(coverage)
        if learning_agility < 60 or engineering_ability < 60:
            final_score = min(final_score, 69.0)
        elif skill_coverage_ratio < 0.5:
            final_score = min(final_score, 74.0)
        # Add market-benchmark commentary
        summary_raw = str(llm_output.get("summary") or heuristic["summary"])
        market_benchmark = llm_output.get("market_benchmark")
        if market_benchmark:
            summary_raw = f"【市场对标】{market_benchmark}\n{summary_raw}"

        return {
            "match_score": match_score,
            "competitiveness_score": competitiveness_score,
            "final_score": final_score,
            "confidence_score": confidence_score,
            "dimension_scores": merged_dimensions,
            "strengths": self._localize_text_list(
                self._dedupe_strings(list(llm_output.get("strengths") or []) or list(heuristic["strengths"]))
            ),
            "weaknesses": self._localize_text_list(
                self._dedupe_strings(list(llm_output.get("weaknesses") or []) or list(heuristic["weaknesses"]))
            ),
            "highlights": self._localize_text_list(
                self._dedupe_strings(list(llm_output.get("highlights") or []) or list(heuristic["highlights"]))
            ),
            "risk_flags": self._dedupe_strings(list(heuristic["risk_flags"]) + list(llm_output.get("risk_flags") or [])),
            "recommendation": llm_output.get("recommendation") or heuristic["recommendation"],
            "summary": self._localize_text(summary_raw),
            "job_requirement_coverage": coverage,
        }

    def _resolve_recommendation(
        self,
        *,
        final_score: float,
        confidence: float,
        decision_action: str,
        risk_flags: list[str],
        dimension_scores: dict[str, Any],
        job_requirement_coverage: dict[str, Any],
    ) -> str:
        # Product rule: 80+ should be recommended directly.
        if final_score >= 80:
            return "strong_recommend" if final_score >= 85 else "recommend"
        learning_agility = self._safe_float(dimension_scores.get("learning_agility")) or 0.0
        engineering_ability = self._safe_float(dimension_scores.get("engineering_ability")) or 0.0
        coverage_ratio = self._coverage_to_ratio(job_requirement_coverage)
        if decision_action == "manual_review":
            return "review"
        if learning_agility < 60 or engineering_ability < 60:
            return "review" if final_score >= 60 else "reject"
        if coverage_ratio < 0.35:
            return "reject"
        if any(flag in {"skills_missing", "project_evidence_weak"} for flag in risk_flags):
            return "review"
        if confidence < 0.55 and final_score >= self._settings.ai_candidate_evaluation_recommend_score:
            return "review"
        if (
            final_score >= self._settings.ai_candidate_evaluation_strong_recommend_score
            and confidence >= 0.80
            and coverage_ratio >= 0.75
            and learning_agility >= 80
            and engineering_ability >= 80
        ):
            return "strong_recommend"
        if final_score >= self._settings.ai_candidate_evaluation_strong_recommend_score and confidence >= 0.75:
            return "recommend"
        if final_score >= self._settings.ai_candidate_evaluation_recommend_score:
            return "recommend"
        return "reject"

    def _calculate_education_score(self, candidate_level: str, required_level: str | None) -> float:
        if not required_level:
            return 75.0 if candidate_level else 60.0
        candidate_rank = _EDUCATION_RANK.get(candidate_level, 0)
        required_rank = _EDUCATION_RANK.get(required_level, 0)
        if candidate_rank >= required_rank:
            return 90.0
        if candidate_rank == 0:
            return 45.0
        gap = required_rank - candidate_rank
        return max(40.0, 82.0 - gap * 18.0)

    def _calculate_project_relevance(
        self,
        *,
        projects: list[Any],
        resume_text: str,
        matched_skills: list[str],
        job_requirements: str,
    ) -> float:
        score = 55.0
        if matched_skills:
            score += min(20.0, len(matched_skills) * 5.0)
        if projects:
            score += min(15.0, len(projects) * 5.0)
        lower_resume = resume_text.lower()
        lower_requirements = (job_requirements or "").lower()
        overlap_hits = sum(1 for token in _SKILL_KEYWORDS if token in lower_resume and token in lower_requirements)
        score += min(10.0, overlap_hits * 2.0)
        return min(score, 95.0)

    def _calculate_internship_score(self, *, resume_text: str, raw_profile: dict[str, Any]) -> tuple[float, int]:
        text = (resume_text or "").lower()
        keyword_hits = len(re.findall(r"(实习|intern|internship)", text))
        profile_hits = 0
        for key in ("internship", "internships", "practice", "实习经历"):
            value = raw_profile.get(key)
            if isinstance(value, list):
                profile_hits += len(value)
            elif value:
                profile_hits += 1
        count = max(keyword_hits, profile_hits)
        score = 45.0 + min(40.0, count * 12.0)
        if any(token in text for token in ("负责", "owner", "独立", "delivered", "上线", "产出")):
            score += 8.0
        return min(score, 95.0), count

    def _calculate_contest_score(self, *, resume_text: str, raw_profile: dict[str, Any]) -> tuple[float, int]:
        text = (resume_text or "").lower()
        keyword_hits = len(re.findall(r"(竞赛|比赛|获奖|award|acm|挑战赛|hackathon)", text))
        profile_hits = 0
        for key in ("awards", "award", "contests", "competition", "honors", "获奖", "竞赛"):
            value = raw_profile.get(key)
            if isinstance(value, list):
                profile_hits += len(value)
            elif value:
                profile_hits += 1
        count = max(keyword_hits, profile_hits)
        score = 42.0 + min(42.0, count * 10.0)
        return min(score, 92.0), count

    def _calculate_academic_score(
        self,
        *,
        resume_text: str,
        normalized_profile: dict[str, Any],
        raw_profile: dict[str, Any],
    ) -> tuple[float, float | None]:
        education_level = str(normalized_profile.get("education_level") or "").strip()
        education_base = {
            "博士": 90.0,
            "硕士": 82.0,
            "本科": 74.0,
            "大专": 66.0,
            "中专": 58.0,
            "高中": 52.0,
        }.get(education_level, 60.0)

        gpa_value = self._extract_gpa(resume_text=resume_text, raw_profile=raw_profile)
        if gpa_value is None:
            return min(education_base, 92.0), None
        # Normalize to a 4.0 scale when possible.
        normalized_gpa = gpa_value / 25.0 if gpa_value > 4.5 else gpa_value
        gpa_score = max(45.0, min(95.0, 45.0 + normalized_gpa * 12.0))
        final = round(education_base * 0.45 + gpa_score * 0.55, 2)
        return min(final, 95.0), normalized_gpa

    def _extract_gpa(self, *, resume_text: str, raw_profile: dict[str, Any]) -> float | None:
        for key in ("gpa", "GPA", "grade", "成绩", "绩点"):
            value = raw_profile.get(key)
            try:
                if value is not None and str(value).strip():
                    return float(str(value).strip())
            except (TypeError, ValueError):
                continue
        text = resume_text or ""
        match_4 = re.search(r"(?:GPA|绩点)\s*[:：]?\s*(\d(?:\.\d+)?)\s*/\s*4(?:\.0)?", text, re.IGNORECASE)
        if match_4:
            return self._safe_float(match_4.group(1))
        match_100 = re.search(r"(?:平均分|成绩|grade)\s*[:：]?\s*(\d{2}(?:\.\d+)?)", text, re.IGNORECASE)
        if match_100:
            return self._safe_float(match_100.group(1))
        return None

    def _calculate_stability_score(self, *, raw_profile: dict[str, Any], resume_risks: list[Any]) -> float:
        score = 82.0
        job_hops = raw_profile.get("job_hops")
        try:
            if job_hops is not None:
                score -= max(0, int(job_hops) - 1) * 6.0
        except (TypeError, ValueError):
            pass
        for risk in resume_risks:
            level = str(getattr(risk, "risk_level", "")).lower()
            if level == "high":
                score -= 12.0
            elif level == "medium":
                score -= 6.0
            else:
                score -= 2.0
        return max(35.0, min(score, 92.0))

    def _calculate_resume_completeness(self, *, resume_text: str, normalized_profile: dict[str, Any]) -> float:
        score = 40.0
        if len(resume_text.strip()) >= 80:
            score += 15.0
        if normalized_profile.get("skills"):
            score += 15.0
        if normalized_profile.get("experience_years") is not None:
            score += 10.0
        if normalized_profile.get("education_level"):
            score += 8.0
        if normalized_profile.get("projects"):
            score += 12.0
        return min(score, 95.0)

    def _calculate_learning_agility(
        self,
        *,
        internship_score: float,
        contest_score: float,
        academic_score: float,
        project_relevance: float,
        resume_completeness: float,
        candidate_years: float | None,
        requirement_signals: _JobRequirementSignals,
    ) -> float:
        score = (
            internship_score * 0.20
            + contest_score * 0.12
            + academic_score * 0.18
            + project_relevance * 0.22
            + resume_completeness * 0.12
            + 66.0 * 0.16
        )
        if candidate_years is not None and candidate_years <= 2.0:
            score += 4.0
        if requirement_signals.min_years and candidate_years is not None and candidate_years >= requirement_signals.min_years:
            score += 2.0
        return round(max(35.0, min(score, 96.0)), 2)

    def _calculate_engineering_ability(
        self,
        *,
        skill_match: float,
        experience_match: float,
        project_relevance: float,
        stability_score: float,
        jd_coverage: float,
    ) -> float:
        score = (
            skill_match * 0.34
            + experience_match * 0.18
            + project_relevance * 0.30
            + jd_coverage * 0.12
            + stability_score * 0.06
        )
        return round(max(30.0, min(score, 97.0)), 2)

    def _estimate_requirement_strictness(
        self,
        *,
        required_skills: set[str],
        min_years: float | None,
        education_level: str | None,
        requirement_text: str,
    ) -> float:
        strictness = 45.0 + min(35.0, len(required_skills) * 4.0)
        if min_years is not None:
            strictness += min(10.0, max(0.0, min_years) * 1.5)
        if education_level:
            strictness += 6.0
        text = (requirement_text or "").lower()
        if any(token in text for token in ("必须", "必备", "must", "强制", "required")):
            strictness += 8.0
        return max(35.0, min(strictness, 95.0))

    def _estimate_evidence_quality(
        self,
        *,
        resume_text: str,
        projects: list[Any],
        internship_count: int,
        contest_count: int,
        gpa_value: float | None,
        matched_skills: list[str],
        required_skills: set[str],
    ) -> float:
        quality = 35.0
        text = (resume_text or "").strip()
        if len(text) >= 250:
            quality += 15.0
        elif len(text) >= 120:
            quality += 8.0
        if projects:
            quality += min(16.0, len(projects) * 5.0)
        if internship_count > 0:
            quality += min(10.0, internship_count * 3.0)
        if contest_count > 0:
            quality += min(8.0, contest_count * 2.5)
        if gpa_value is not None:
            quality += 6.0
        if required_skills:
            quality += min(20.0, (len(matched_skills) / max(1, len(required_skills))) * 20.0)
        elif matched_skills:
            quality += min(10.0, len(matched_skills) * 2.0)
        if re.search(r"\d+(\.\d+)?\s*(%|ms|qps|w|万|亿|倍)", text.lower()):
            quality += 6.0
        return max(20.0, min(quality, 95.0))

    def _estimate_risk_penalty(
        self,
        *,
        risk_flags: list[str],
        resume_risks: list[Any],
        jd_coverage: float,
        requirement_strictness: float,
    ) -> float:
        penalty = 0.0
        high_impact_flags = {
            "skill_match_low",
            "skills_missing",
            "project_evidence_weak",
            "resume_completeness_low",
            "academic_performance_weak",
            "contest_evidence_weak",
            "learning_agility_low",
            "engineering_ability_low",
        }
        penalty += sum(3.0 for flag in set(risk_flags) if flag in high_impact_flags)
        for risk in resume_risks:
            level = str(getattr(risk, "risk_level", "")).lower()
            if level == "high":
                penalty += 5.0
            elif level == "medium":
                penalty += 2.5
            elif level:
                penalty += 1.0
        if jd_coverage < 60:
            penalty += (60.0 - jd_coverage) * 0.12
        if requirement_strictness >= 80 and jd_coverage < 70:
            penalty += 4.0
        return max(0.0, min(penalty, 28.0))

    def _calibrate_final_score(
        self,
        *,
        base_final: float,
        jd_coverage: float,
        requirement_strictness: float,
        evidence_quality: float,
        risk_penalty: float,
    ) -> float:
        # Wide-range calibration: stronger requirements + weak evidence/risk will pull score down,
        # while high coverage + high quality can lift strong candidates.
        calibrated = float(base_final)
        calibrated += (evidence_quality - 60.0) * 0.18
        calibrated += (jd_coverage - 65.0) * 0.16
        calibrated -= risk_penalty
        if requirement_strictness >= 80 and jd_coverage < 75:
            calibrated -= 3.0
        return round(max(35.0, min(calibrated, 98.0)), 2)

    def _build_summary(
        self,
        *,
        final_score: float,
        match_score: float,
        competitiveness_score: float,
        matched_skills: list[str],
        weaknesses: list[str],
    ) -> str:
        strengths_text = f"技能重合点集中在 {', '.join(matched_skills[:3])}" if matched_skills else "技能重合证据偏弱"
        weakness_text = f"；主要短板：{weaknesses[0]}" if weaknesses else ""
        return (
            f"综合评分 {final_score:.1f}，岗位匹配度 {match_score:.1f}，候选人竞争力 {competitiveness_score:.1f}。"
            f"{strengths_text}{weakness_text}。"
        )

    def _pipeline_to_dict(self, pipeline) -> dict[str, Any]:
        return {
            "id": pipeline.id,
            "candidate_id": pipeline.candidate_id,
            "job_id": pipeline.job_id,
            "resume_request_status": pipeline.resume_request_status,
            "resume_download_status": pipeline.resume_download_status,
            "evaluation_status": pipeline.evaluation_status,
            "invitation_status": pipeline.invitation_status,
            "latest_evaluation_id": pipeline.latest_evaluation_id,
            "latest_invitation_id": pipeline.latest_invitation_id,
            "last_evaluated_at": pipeline.last_evaluated_at,
            "payload": pipeline.payload or {},
        }

    def _sync_candidate_summary(
        self,
        *,
        candidate_id: str,
        final_score: float,
        dimension_scores: dict[str, float],
        summary: str,
    ) -> None:
        candidate = self._candidate_repository.get(candidate_id)
        candidate.score_total = final_score
        candidate.score_dimensions = dimension_scores
        candidate.score_explanation = summary
        candidate.scored_at = datetime.now(UTC).replace(tzinfo=None)
        if candidate.current_stage in {"new", "parsed"}:
            candidate.current_stage = "screen_pass" if final_score >= 70 else "parsed"

    def _to_response(self, entity) -> CandidateEvaluationResponse:
        return CandidateEvaluationResponse(
            id=entity.id,
            candidate_id=entity.candidate_id,
            job_id=entity.job_id,
            resume_attachment_id=entity.resume_attachment_id,
            evaluation_version=entity.evaluation_version,
            source=entity.source,
            status=entity.status,
            match_score=float(entity.match_score),
            competitiveness_score=float(entity.competitiveness_score),
            final_score=float(entity.final_score),
            confidence_score=float(entity.confidence_score) if entity.confidence_score is not None else None,
            recommendation=entity.recommendation,
            summary=entity.summary,
            dimension_scores={k: float(v) for k, v in dict(entity.dimension_scores or {}).items()},
            strengths=[str(item) for item in list(entity.strengths or [])],
            weaknesses=[str(item) for item in list(entity.weaknesses or [])],
            highlights=[str(item) for item in list(entity.highlights or [])],
            risk_flags=[str(item) for item in list(entity.risk_flags or [])],
            job_requirement_coverage={str(k): str(v) for k, v in dict(entity.job_requirement_coverage or {}).items()},
            raw_llm_output=entity.raw_llm_output,
            invited_flag=bool(entity.invited_flag),
            reviewed_by=entity.reviewed_by,
            reviewed_at=entity.reviewed_at,
            evaluated_at=entity.evaluated_at,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    def _is_llm_enabled(self) -> bool:
        return self._runtime_repository.is_feature_enabled(
            feature_key="ai_candidate_evaluation_llm",
            default_enabled=self._settings.ai_candidate_evaluation_llm_enabled,
        )

    def _dedupe_strings(self, values: list[Any]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for value in values:
            text = str(value).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            deduped.append(text)
        return deduped

    def _safe_float(self, value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _sanitize_string_list(self, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        return [item.strip() for item in values if item and item.strip()]

    def _localize_text_list(self, values: list[str]) -> list[str]:
        return [self._localize_text(value) for value in values]

    def _localize_text(self, text: str) -> str:
        normalized = str(text or "").strip()
        if not normalized:
            return ""
        exact_map = {
            "core_stack_aligned": "核心技术栈匹配度高",
            "resume_contains_project_context": "简历包含项目上下文信息",
            "insufficient_quantified_impact": "量化成果描述不足",
            "candidate_shows_direct_stack_overlap": "候选人与岗位技术栈直接重合",
            "mock detailed evaluation output": "模拟评估结果",
        }
        mapped = exact_map.get(normalized.lower()) or exact_map.get(normalized)
        if mapped:
            return mapped
        prefix_map = {
            "core skills aligned:": "核心技能匹配度高：",
            "matched_skill:": "匹配技能：",
            "final_score:": "最终得分：",
        }
        lower = normalized.lower()
        for prefix, zh_prefix in prefix_map.items():
            if lower.startswith(prefix):
                return zh_prefix + normalized[len(prefix):].strip()
        return normalized

    def _build_candidate_matching_directive(
        self,
        *,
        requirement_signals: _JobRequirementSignals,
        resume_risk_count: int,
    ) -> str:
        required_skills = ", ".join(requirement_signals.skills[:8]) if requirement_signals.skills else "none"
        min_years = str(requirement_signals.min_years) if requirement_signals.min_years is not None else "not_specified"
        education = requirement_signals.education_level or "not_specified"
        return (
            "Strict evaluation policy:\n"
            "1) Prioritize mismatch detection before strengths.\n"
            "2) Evidence-first: without concrete engineering evidence (trade-off, debugging, performance, delivery), engineering_ability must be <= 60.\n"
            "3) Without rapid-learning evidence (new domain ramp-up, compressed learning cycle, measurable learning output), learning_agility must be <= 65.\n"
            "4) Keep score distribution realistic for competitive market; reserve 85+ for clearly exceptional candidates.\n"
            "5) recommendation must align with dimensions and risk flags; do not over-recommend.\n"
            f"JD hard signals: required_skills={required_skills}; min_years={min_years}; education={education}; resume_risk_count={resume_risk_count}.\n"
            "Output JSON only."
        )

    def _extract_dimension_score(self, *, merged_dimensions: dict[str, float], heuristic: dict[str, Any], key: str) -> float:
        value = merged_dimensions.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        heuristic_value = heuristic.get("dimension_scores", {}).get(key)
        if isinstance(heuristic_value, (int, float)):
            return float(heuristic_value)
        return 0.0

    def _coverage_to_ratio(self, coverage: dict[str, Any]) -> float:
        if not coverage:
            return 1.0
        non_skill_keys = {"education_requirement", "internship_signal", "project_signal", "contest_signal", "grade_signal"}
        skill_values = [
            str(value).strip().lower()
            for key, value in coverage.items()
            if str(key).strip().lower() not in non_skill_keys
        ]
        if not skill_values:
            return 1.0
        matched = sum(1 for value in skill_values if value == "matched")
        partial = sum(1 for value in skill_values if value == "partial")
        return max(0.0, min((matched + partial * 0.5) / len(skill_values), 1.0))


def get_candidate_evaluation_service(session: Session) -> CandidateEvaluationService:
    """Return a candidate evaluation service bound to the current session."""

    return CandidateEvaluationService(session)
