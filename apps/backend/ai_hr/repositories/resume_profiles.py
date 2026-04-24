"""Resume profile repository."""

from __future__ import annotations
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from ..db.models import CandidateResumeProfile, CandidateResumeRisk


class ResumeProfileRepository:
    """Handles persistence for resume parse results and risk tags."""

    def __init__(self, session: Session):
        self._session = session

    def get_profile(self, candidate_id: str) -> CandidateResumeProfile | None:
        """Return the resume profile for a candidate, or None if not found."""
        stmt = select(CandidateResumeProfile).where(CandidateResumeProfile.candidate_id == candidate_id)
        return self._session.execute(stmt).scalar_one_or_none()

    def list_risks(self, candidate_id: str) -> list[CandidateResumeRisk]:
        """Return all risk tags for a candidate."""
        stmt = select(CandidateResumeRisk).where(CandidateResumeRisk.candidate_id == candidate_id)
        return list(self._session.execute(stmt).scalars().all())

    def upsert_profile(
        self,
        *,
        candidate_id: str,
        raw_text: str,
        parsed_json: dict,
        normalized_json: dict,
        parse_status: str,
        parser_version: str,
        confidence: float,
    ) -> CandidateResumeProfile:
        """Insert or update a resume profile."""
        profile = self.get_profile(candidate_id)
        if profile is None:
            profile = CandidateResumeProfile(
                candidate_id=candidate_id,
                raw_text=raw_text,
                parsed_json=parsed_json,
                normalized_json=normalized_json,
                parse_status=parse_status,
                parser_version=parser_version,
                confidence=confidence,
            )
            self._session.add(profile)
        else:
            profile.raw_text = raw_text
            profile.parsed_json = parsed_json
            profile.normalized_json = normalized_json
            profile.parse_status = parse_status
            profile.parser_version = parser_version
            profile.confidence = confidence
        self._session.flush()
        return profile

    def replace_risks(self, *, candidate_id: str, risks: list[dict[str, str]]) -> list[CandidateResumeRisk]:
        """Replace all risk tags for a candidate."""
        self._session.execute(delete(CandidateResumeRisk).where(CandidateResumeRisk.candidate_id == candidate_id))
        entities: list[CandidateResumeRisk] = []
        for item in risks:
            entity = CandidateResumeRisk(
                candidate_id=candidate_id,
                risk_code=item["risk_code"],
                risk_level=item["risk_level"],
                detail=item["detail"],
            )
            self._session.add(entity)
            entities.append(entity)
        self._session.flush()
        return entities
