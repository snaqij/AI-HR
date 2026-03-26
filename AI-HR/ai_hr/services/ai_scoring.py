"""AI 批量评分、排序与入围名单服务。"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.exceptions import InvalidStateError
from ..repositories.ai_observability import AIObservabilityRepository
from ..repositories.ai_runtime import AIRuntimeRepository
from ..repositories.ai_scoring import AIScoringRepository
from ..repositories.jobs import JobRepository
from ..schemas.ai_scoring import (
    AICandidateBatchScoreRequest,
    AICandidateBatchScoreResult,
    AICandidateRankRequest,
    AICandidateRankResult,
    AICandidateScoreItem,
    AIShortlistItem,
    JobShortlistResult,
)
from ..schemas.candidates import CandidateResponse
from .llm.client import InvokeContext, LLMClient
from .llm.guardrails import GuardrailService
from .llm.prompts import get_prompt_template
from .llm.router import ModelRouter
from .policy.decision import PolicyDecisionService
from .scoring import score_candidate_profile


class AIScoringService:
    """负责岗位维度的批量评分与排序入围。"""

    def __init__(self, session: Session):
        """注入数据库会话并初始化依赖。"""
        self._session = session
        self._settings = get_settings()
        self._job_repository = JobRepository(session)
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

    def batch_score(self, payload: AICandidateBatchScoreRequest) -> AICandidateBatchScoreResult:
        """按岗位批量执行 AI 评分并持久化。"""
        job = self._job_repository.get(payload.job_id)
        candidates = self._scoring_repository.list_candidates(payload.candidate_ids)
        if not candidates:
            raise InvalidStateError("No candidates found for batch scoring")

        for candidate in candidates:
            base_scoring = score_candidate_profile(
                resume_text=candidate.resume_text,
                profile=candidate.raw_profile or {},
                job_requirements=job.requirements,
            )
            final_total = base_scoring.total_score
            final_dimensions = dict(base_scoring.dimensions)
            final_explanation = base_scoring.explanation
            risk_tags = list(base_scoring.risk_tags)
            score_version = base_scoring.score_version
            confidence = 0.68

            if self._is_llm_enabled():
                llm_output = self._score_with_llm(
                    candidate_id=candidate.id,
                    job_requirements=job.requirements,
                    resume_text=candidate.resume_text or "",
                    profile=candidate.raw_profile or {},
                )
                if llm_output:
                    llm_score = float(llm_output.get("total_score", final_total))
                    final_total = round(final_total * 0.4 + llm_score * 0.6, 2)
                    llm_dimensions = llm_output.get("dimension_scores", {})
                    if isinstance(llm_dimensions, dict):
                        for key, value in llm_dimensions.items():
                            try:
                                final_dimensions[str(key)] = round(float(value), 2)
                            except (TypeError, ValueError):
                                continue
                    final_explanation = f"{base_scoring.explanation}; llm={llm_output.get('explanation', '')}".strip("; ")
                    risk_tags.extend([str(item) for item in llm_output.get("risk_tags", [])])
                    score_version = "hybrid-v1"
                    confidence = 0.8
                else:
                    risk_tags.append("llm_unavailable")

            for risk in candidate.resume_risks:
                if risk.risk_code not in risk_tags:
                    risk_tags.append(risk.risk_code)

            policy = self._policy_service.decide_score_action(confidence=confidence, risk_tags=risk_tags)
            risk_tags = list(dict.fromkeys(risk_tags + policy.policy_flags))

            self._scoring_repository.upsert_job_score(
                candidate_id=candidate.id,
                job_id=job.id,
                total_score=final_total,
                dimension_scores=final_dimensions,
                explanation=final_explanation,
                risk_tags=risk_tags,
                score_version=score_version,
            )

        self._session.commit()
        scores = self._sorted_scores(self._scoring_repository.list_job_scores(job.id))
        return AICandidateBatchScoreResult(
            job_id=job.id,
            scored_count=len(scores),
            results=[
                AICandidateScoreItem(
                    candidate_id=item.candidate_id,
                    total_score=item.total_score,
                    dimension_scores=item.dimension_scores or {},
                    explanation=item.explanation,
                    risk_tags=item.risk_tags or [],
                    score_version=item.score_version,
                    scored_at=item.scored_at,
                )
                for item in scores
            ],
        )

    def rank_candidates(self, payload: AICandidateRankRequest) -> AICandidateRankResult:
        """基于评分结果计算排序并生成 shortlist。"""
        self._job_repository.get(payload.job_id)
        all_scores = self._sorted_scores(self._scoring_repository.list_job_scores(payload.job_id))
        if not all_scores:
            raise InvalidStateError("No scored candidates for this job")

        filtered = all_scores
        if payload.min_score is not None:
            filtered = [item for item in all_scores if item.total_score >= payload.min_score]

        selected = filtered[: payload.top_n]
        shortlist_candidate_ids = [item.candidate_id for item in selected]
        self._scoring_repository.replace_shortlist(job_id=payload.job_id, candidate_ids=shortlist_candidate_ids)
        self._session.commit()

        return AICandidateRankResult(
            job_id=payload.job_id,
            top_n=payload.top_n,
            shortlist=self._to_shortlist_items(selected),
        )

    def get_job_shortlist(self, job_id: str) -> JobShortlistResult:
        """查询岗位入围名单。"""
        self._job_repository.get(job_id)
        shortlist_entities = self._scoring_repository.list_shortlist(job_id)
        if not shortlist_entities:
            return JobShortlistResult(job_id=job_id, shortlist=[])

        score_map = {item.candidate_id: item for item in self._scoring_repository.list_job_scores(job_id)}
        items: list[AIShortlistItem] = []
        for entry in shortlist_entities:
            score = score_map.get(entry.candidate_id)
            if score is None:
                continue
            items.append(
                AIShortlistItem(
                    rank=entry.rank,
                    candidate=CandidateResponse.model_validate(entry.candidate),
                    total_score=score.total_score,
                    dimension_scores=score.dimension_scores or {},
                    risk_tags=score.risk_tags or [],
                    score_version=score.score_version,
                    scored_at=score.scored_at,
                )
            )
        return JobShortlistResult(job_id=job_id, shortlist=items)

    def _score_with_llm(
        self,
        *,
        candidate_id: str,
        job_requirements: str,
        resume_text: str,
        profile: dict,
    ) -> dict | None:
        """调用 LLM 计算候选人评分补充信息。"""
        template = get_prompt_template("candidate_score", "v1")
        prompt = "\n".join(
            [
                template.system_prompt,
                template.render(
                    job_requirements=job_requirements,
                    candidate_profile={"resume_text": resume_text, "profile": profile},
                ),
            ]
        )
        result = self._llm_client.invoke_json(
            InvokeContext(
                task_key="candidate_score",
                trace_id=str(uuid.uuid4()),
                prompt=prompt,
                entity_type="candidate",
                entity_id=candidate_id,
            )
        )
        if result.fallback_used or result.content.get("error"):
            return None
        return result.content

    def _sorted_scores(self, scores):
        """按总分降序、候选人 ID 升序实现稳定排序。"""
        return sorted(scores, key=lambda item: (-item.total_score, item.candidate_id))

    def _to_shortlist_items(self, scores) -> list[AIShortlistItem]:
        """将评分实体转换为 shortlist 响应结构。"""
        items: list[AIShortlistItem] = []
        for index, score in enumerate(scores, start=1):
            items.append(
                AIShortlistItem(
                    rank=index,
                    candidate=CandidateResponse.model_validate(score.candidate),
                    total_score=score.total_score,
                    dimension_scores=score.dimension_scores or {},
                    risk_tags=score.risk_tags or [],
                    score_version=score.score_version,
                    scored_at=score.scored_at,
                )
            )
        return items

    def _is_llm_enabled(self) -> bool:
        """判定评分链路是否启用 LLM。"""
        return self._runtime_repository.is_feature_enabled(
            feature_key="ai_scoring_llm",
            default_enabled=self._settings.ai_scoring_llm_enabled,
        )


def get_ai_scoring_service(session: Session) -> AIScoringService:
    """返回绑定当前数据库会话的 AIScoringService。"""
    return AIScoringService(session)
