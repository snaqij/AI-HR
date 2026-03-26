"""Candidate services."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..repositories.candidates import CandidateRepository
from ..repositories.jobs import JobRepository
from ..schemas.candidates import CandidateImportRequest, CandidateScoreRequest
from .scoring import score_candidate_profile


class CandidateService:
    def __init__(self, repository: CandidateRepository, job_repository: JobRepository):
        self._repository = repository
        self._job_repository = job_repository

    def import_candidates(self, payload: CandidateImportRequest):
        candidates, created_count, updated_count = self._repository.upsert_many(payload.candidates)
        return {
            "created_count": created_count,
            "updated_count": updated_count,
            "candidates": candidates,
        }

    def score_candidate(self, candidate_id: str, payload: CandidateScoreRequest):
        candidate = self._repository.get(candidate_id)
        job_requirements = None
        if payload.job_id:
            job = self._job_repository.get(payload.job_id)
            job_requirements = job.requirements

        scoring = score_candidate_profile(
            resume_text=candidate.resume_text,
            profile=candidate.raw_profile,
            job_requirements=job_requirements,
        )
        updated = self._repository.update_score(
            candidate_id,
            total_score=scoring.total_score,
            dimensions=scoring.dimensions,
            explanation=scoring.explanation,
        )
        return {
            "candidate": updated,
            "total_score": scoring.total_score,
            "dimensions": scoring.dimensions,
            "explanation": scoring.explanation,
        }



def get_candidate_service(session: Session) -> CandidateService:
    return CandidateService(CandidateRepository(session), JobRepository(session))
