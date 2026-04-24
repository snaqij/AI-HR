"""Candidate repository implementation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, load_only

from ..core.exceptions import ResourceNotFoundError
from ..db.models import Candidate, CandidateIdentity
from ..schemas.candidates import CandidateImportItem
from .workspace_scope import get_workspace_id


class CandidateRepository:
    """Encapsulates candidate reads/writes, dedup merge and score updates."""

    def __init__(self, session: Session):
        self._session = session

    def upsert_many(self, items: list[CandidateImportItem]) -> tuple[list[Candidate], int, int]:
        created = 0
        updated = 0
        entities: list[Candidate] = []
        workspace_id = get_workspace_id(self._session)

        for item in items:
            candidate = self._find_by_identity(item.source_channel, item.external_candidate_id)

            if candidate is None:
                dedup_candidate = self._find_master_candidate_for_merge(item)
                if dedup_candidate is None:
                    candidate = Candidate(
                        workspace_id=workspace_id,
                        name=item.name,
                        source_channel=item.source_channel,
                        external_candidate_id=item.external_candidate_id,
                        phone_hash=item.phone_hash,
                        email_hash=item.email_hash,
                        email=item.email,
                        resume_url=item.resume_url,
                        resume_text=item.resume_text,
                        school=item.school,
                        degree=item.degree,
                        work_experience=item.work_experience,
                        expected_salary=item.expected_salary,
                        latest_company=item.latest_company,
                        raw_profile=item.raw_profile,
                        current_stage="new",
                    )
                    self._session.add(candidate)
                    self._session.flush()
                    self._ensure_identity(candidate, item.source_channel, item.external_candidate_id)
                    created += 1
                else:
                    candidate = dedup_candidate
                    self._apply_updates(candidate, item)
                    self._ensure_identity(candidate, item.source_channel, item.external_candidate_id)
                    updated += 1
            else:
                self._apply_updates(candidate, item)
                self._ensure_identity(candidate, item.source_channel, item.external_candidate_id)
                updated += 1

            entities.append(candidate)

        self._session.commit()
        for entity in entities:
            self._session.refresh(entity)
        return entities, created, updated

    def get(self, candidate_id: str) -> Candidate:
        stmt = select(Candidate).where(Candidate.id == candidate_id)
        workspace_id = get_workspace_id(self._session)
        if workspace_id:
            stmt = stmt.where(Candidate.workspace_id == workspace_id)
        candidate = self._session.execute(stmt).scalar_one_or_none()
        if candidate is None:
            raise ResourceNotFoundError(f"Candidate '{candidate_id}' was not found")
        return candidate

    def list_by_ids(self, candidate_ids: list[str], *, summary_only: bool = False) -> list[Candidate]:
        ids = [item for item in dict.fromkeys(candidate_ids) if item]
        if not ids:
            return []
        stmt = select(Candidate).where(Candidate.id.in_(ids))
        workspace_id = get_workspace_id(self._session)
        if workspace_id:
            stmt = stmt.where(Candidate.workspace_id == workspace_id)
        if summary_only:
            stmt = stmt.options(
                load_only(
                    Candidate.id,
                    Candidate.name,
                    Candidate.email,
                    Candidate.current_stage,
                    Candidate.school,
                    Candidate.degree,
                    Candidate.work_experience,
                    Candidate.expected_salary,
                    Candidate.latest_company,
                    Candidate.created_at,
                    Candidate.updated_at,
                )
            )
        return list(self._session.execute(stmt).scalars().all())

    def update_score(
        self,
        candidate_id: str,
        *,
        total_score: float,
        dimensions: dict[str, float],
        explanation: str,
    ) -> Candidate:
        candidate = self.get(candidate_id)
        candidate.score_total = total_score
        candidate.score_dimensions = dimensions
        candidate.score_explanation = explanation
        candidate.scored_at = datetime.now(UTC).replace(tzinfo=None)
        if candidate.current_stage == "new":
            candidate.current_stage = "parsed"
        if candidate.score_total >= 70 and candidate.current_stage in {"new", "parsed"}:
            candidate.current_stage = "screen_pass"
        self._session.commit()
        self._session.refresh(candidate)
        return candidate

    def list_pending_metadata_enrichment(
        self,
        limit: int = 10,
        *,
        candidate_ids: list[str] | None = None,
    ) -> list[Candidate]:
        stmt = (
            select(Candidate)
            .where(
                Candidate.source_channel == "boss",
                Candidate.metadata_synced_at.is_(None),
                or_(
                    Candidate.school.is_(None),
                    Candidate.expected_salary.is_(None),
                ),
            )
            .order_by(Candidate.created_at.desc())
            .limit(limit)
        )
        if candidate_ids:
            ids = [item for item in dict.fromkeys(candidate_ids) if item]
            if not ids:
                return []
            stmt = stmt.where(Candidate.id.in_(ids))
        workspace_id = get_workspace_id(self._session)
        if workspace_id:
            stmt = stmt.where(Candidate.workspace_id == workspace_id)
        return list(self._session.execute(stmt).scalars().all())

    def mark_metadata_synced(self, candidate_id: str) -> None:
        candidate = self.get(candidate_id)
        candidate.metadata_synced_at = datetime.now(UTC).replace(tzinfo=None)
        self._session.commit()

    def update_stage(self, candidate_id: str, stage: str) -> Candidate:
        candidate = self.get(candidate_id)
        candidate.current_stage = stage
        self._session.commit()
        self._session.refresh(candidate)
        return candidate

    def update_resume_fields(
        self,
        candidate_id: str,
        *,
        resume_url: str | None = None,
        resume_text: str | None = None,
        raw_profile_patch: dict[str, Any] | None = None,
    ) -> Candidate:
        candidate = self.get(candidate_id)
        if resume_url:
            candidate.resume_url = resume_url
        if resume_text:
            candidate.resume_text = resume_text
        if raw_profile_patch:
            candidate.raw_profile = self._merge_raw_profile(candidate.raw_profile, raw_profile_patch)
        self._session.commit()
        self._session.refresh(candidate)
        return candidate

    def _find_by_identity(self, source_channel: str, external_candidate_id: str) -> Candidate | None:
        workspace_id = get_workspace_id(self._session)

        for pending in self._session.new:
            if not isinstance(pending, CandidateIdentity):
                continue
            if pending.source_channel != source_channel or pending.external_candidate_id != external_candidate_id:
                continue
            candidate = self._session.get(Candidate, pending.candidate_id)
            if candidate is None:
                continue
            if workspace_id and candidate.workspace_id != workspace_id:
                return None
            return candidate

        identity_stmt = select(CandidateIdentity).where(
            CandidateIdentity.source_channel == source_channel,
            CandidateIdentity.external_candidate_id == external_candidate_id,
        )
        identity = self._session.execute(identity_stmt).scalar_one_or_none()
        if identity is not None:
            candidate = self._session.get(Candidate, identity.candidate_id)
            if candidate is None:
                return None
            if workspace_id and candidate.workspace_id != workspace_id:
                return None
            return candidate

        legacy_stmt = select(Candidate).where(
            Candidate.source_channel == source_channel,
            Candidate.external_candidate_id == external_candidate_id,
        )
        if workspace_id:
            legacy_stmt = legacy_stmt.where(Candidate.workspace_id == workspace_id)
        legacy_candidate = self._session.execute(legacy_stmt).scalar_one_or_none()
        if legacy_candidate is not None:
            self._ensure_identity(legacy_candidate, source_channel, external_candidate_id)
        return legacy_candidate

    def _find_master_candidate_for_merge(self, item: CandidateImportItem) -> Candidate | None:
        workspace_id = get_workspace_id(self._session)
        filters = []
        if item.phone_hash:
            filters.append(Candidate.phone_hash == item.phone_hash)
        if item.email_hash:
            filters.append(Candidate.email_hash == item.email_hash)
        if not filters:
            return None

        stmt = select(Candidate).where(
            Candidate.source_channel == item.source_channel,
            or_(*filters),
        )
        if workspace_id:
            stmt = stmt.where(Candidate.workspace_id == workspace_id)
        return self._session.execute(stmt).scalars().first()

    def _ensure_identity(self, candidate: Candidate, source_channel: str, external_candidate_id: str) -> None:
        for pending in self._session.new:
            if not isinstance(pending, CandidateIdentity):
                continue
            if pending.source_channel != source_channel or pending.external_candidate_id != external_candidate_id:
                continue
            if pending.candidate_id != candidate.id:
                pending.candidate_id = candidate.id
            return

        stmt = select(CandidateIdentity).where(
            CandidateIdentity.source_channel == source_channel,
            CandidateIdentity.external_candidate_id == external_candidate_id,
        )
        identity = self._session.execute(stmt).scalar_one_or_none()
        if identity is None:
            identity = CandidateIdentity(
                candidate_id=candidate.id,
                source_channel=source_channel,
                external_candidate_id=external_candidate_id,
            )
            self._session.add(identity)
            self._session.flush()
            return

        if identity.candidate_id != candidate.id:
            workspace_id = get_workspace_id(self._session)
            existing_candidate = self._session.get(Candidate, identity.candidate_id)
            if workspace_id and existing_candidate is not None and existing_candidate.workspace_id != workspace_id:
                return
            identity.candidate_id = candidate.id

    def _apply_updates(self, candidate: Candidate, item: CandidateImportItem) -> None:
        candidate.name = item.name
        if item.phone_hash:
            candidate.phone_hash = item.phone_hash
        if item.email_hash:
            candidate.email_hash = item.email_hash
        if item.email:
            candidate.email = item.email
        if item.resume_url:
            candidate.resume_url = item.resume_url
        if item.resume_text:
            candidate.resume_text = item.resume_text
        if item.school:
            candidate.school = item.school
        if item.degree:
            candidate.degree = item.degree
        if item.work_experience:
            candidate.work_experience = item.work_experience
        if item.expected_salary:
            candidate.expected_salary = item.expected_salary
        if item.latest_company:
            candidate.latest_company = item.latest_company
        candidate.raw_profile = self._merge_raw_profile(candidate.raw_profile, item.raw_profile)

    def _merge_raw_profile(self, existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        merged = dict(existing or {})
        for key, value in (incoming or {}).items():
            merged[key] = value
        return merged
