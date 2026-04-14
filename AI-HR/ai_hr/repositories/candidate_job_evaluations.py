"""Repository for candidate-job evaluation records."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.exceptions import InvalidStateError, ResourceNotFoundError
from ..db.models import Candidate, CandidateJobEvaluation, CandidateResumeAttachment, Job


class CandidateJobEvaluationRepository:
    """Persists detailed evaluation results and enforces app-level relations."""

    def __init__(self, session: Session):
        self._session = session

    def get(self, evaluation_id: str) -> CandidateJobEvaluation:
        entity = self._session.get(CandidateJobEvaluation, evaluation_id)
        if entity is None:
            raise ResourceNotFoundError(f"Candidate job evaluation '{evaluation_id}' was not found")
        return entity

    def get_by_version(self, *, candidate_id: str, job_id: str, evaluation_version: str) -> CandidateJobEvaluation | None:
        stmt = select(CandidateJobEvaluation).where(
            CandidateJobEvaluation.candidate_id == candidate_id,
            CandidateJobEvaluation.job_id == job_id,
            CandidateJobEvaluation.evaluation_version == evaluation_version,
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def list_by_job(
        self,
        job_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
        candidate_ids: list[str] | None = None,
    ) -> list[CandidateJobEvaluation]:
        stmt = select(CandidateJobEvaluation).where(CandidateJobEvaluation.job_id == job_id)
        if candidate_ids:
            stmt = stmt.where(CandidateJobEvaluation.candidate_id.in_(candidate_ids))
        stmt = stmt.order_by(CandidateJobEvaluation.final_score.desc(), CandidateJobEvaluation.updated_at.desc())
        stmt = stmt.limit(max(1, limit)).offset(max(0, offset))
        return list(self._session.execute(stmt).scalars().all())

    def get_latest_by_candidate_job(self, *, candidate_id: str, job_id: str) -> CandidateJobEvaluation | None:
        stmt = (
            select(CandidateJobEvaluation)
            .where(
                CandidateJobEvaluation.candidate_id == candidate_id,
                CandidateJobEvaluation.job_id == job_id,
            )
            .order_by(CandidateJobEvaluation.evaluated_at.desc(), CandidateJobEvaluation.updated_at.desc())
            .limit(1)
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def update(
        self,
        evaluation_id: str,
        *,
        recommendation: str | None = None,
        summary: str | None = None,
        strengths: list[Any] | None = None,
        weaknesses: list[Any] | None = None,
        highlights: list[Any] | None = None,
        risk_flags: list[Any] | None = None,
        reviewed_by: str | None = None,
    ) -> CandidateJobEvaluation:
        entity = self.get(evaluation_id)
        if recommendation is not None:
            entity.recommendation = recommendation
        if summary is not None:
            entity.summary = summary
        if strengths is not None:
            entity.strengths = strengths
        if weaknesses is not None:
            entity.weaknesses = weaknesses
        if highlights is not None:
            entity.highlights = highlights
        if risk_flags is not None:
            entity.risk_flags = risk_flags
        if reviewed_by:
            entity.reviewed_by = reviewed_by
            entity.reviewed_at = datetime.now(UTC).replace(tzinfo=None)
            entity.status = "reviewed"
        self._session.flush()
        return entity

    def create(
        self,
        *,
        candidate_id: str,
        job_id: str,
        evaluation_version: str = "v1",
        resume_attachment_id: str | None = None,
        source: str = "hybrid",
        status: str = "completed",
        match_score: float = 0,
        competitiveness_score: float = 0,
        final_score: float = 0,
        confidence_score: float | None = None,
        recommendation: str = "review",
        summary: str | None = None,
        dimension_scores: dict[str, Any] | None = None,
        strengths: list[Any] | None = None,
        weaknesses: list[Any] | None = None,
        highlights: list[Any] | None = None,
        risk_flags: list[Any] | None = None,
        job_requirement_coverage: dict[str, Any] | None = None,
        raw_llm_output: dict[str, Any] | None = None,
    ) -> CandidateJobEvaluation:
        self._assert_candidate_exists(candidate_id)
        self._assert_job_exists(job_id)
        self._assert_resume_attachment_exists(resume_attachment_id)
        if self.get_by_version(candidate_id=candidate_id, job_id=job_id, evaluation_version=evaluation_version):
            raise InvalidStateError(
                f"Evaluation already exists for candidate '{candidate_id}', job '{job_id}', version '{evaluation_version}'"
            )
        now = datetime.now(UTC).replace(tzinfo=None)
        entity = CandidateJobEvaluation(
            candidate_id=candidate_id,
            job_id=job_id,
            resume_attachment_id=resume_attachment_id,
            evaluation_version=evaluation_version,
            source=source,
            status=status,
            match_score=self._to_decimal(match_score),
            competitiveness_score=self._to_decimal(competitiveness_score),
            final_score=self._to_decimal(final_score),
            confidence_score=self._to_decimal(confidence_score) if confidence_score is not None else None,
            recommendation=recommendation,
            summary=summary,
            dimension_scores=dimension_scores,
            strengths=strengths,
            weaknesses=weaknesses,
            highlights=highlights,
            risk_flags=risk_flags,
            job_requirement_coverage=job_requirement_coverage,
            raw_llm_output=raw_llm_output,
            evaluated_at=now,
        )
        self._session.add(entity)
        self._session.flush()
        return entity

    def mark_invited(self, evaluation_id: str, *, invited: bool = True) -> CandidateJobEvaluation:
        entity = self.get(evaluation_id)
        entity.invited_flag = invited
        self._session.flush()
        return entity

    def mark_reviewed(self, evaluation_id: str, *, reviewed_by: str) -> CandidateJobEvaluation:
        entity = self.get(evaluation_id)
        entity.status = "reviewed"
        entity.reviewed_by = reviewed_by
        entity.reviewed_at = datetime.now(UTC).replace(tzinfo=None)
        self._session.flush()
        return entity

    def _assert_candidate_exists(self, candidate_id: str) -> None:
        if self._session.get(Candidate, candidate_id) is None:
            raise ResourceNotFoundError(f"Candidate '{candidate_id}' was not found")

    def _assert_job_exists(self, job_id: str) -> None:
        if self._session.get(Job, job_id) is None:
            raise ResourceNotFoundError(f"Job '{job_id}' was not found")

    def _assert_resume_attachment_exists(self, resume_attachment_id: str | None) -> None:
        if resume_attachment_id and self._session.get(CandidateResumeAttachment, resume_attachment_id) is None:
            raise ResourceNotFoundError(f"Candidate resume attachment '{resume_attachment_id}' was not found")

    def _to_decimal(self, value: float | int) -> Decimal:
        return Decimal(str(round(float(value), 2)))
