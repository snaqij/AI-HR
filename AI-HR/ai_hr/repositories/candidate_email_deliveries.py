"""Repository for candidate email deliveries."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.exceptions import ResourceNotFoundError
from ..db.models import AIInterviewInvitation, Candidate, CandidateEmailDelivery, CandidateJobEvaluation, Job


class CandidateEmailDeliveryRepository:
    """Handles creation and delivery state transitions for outbound emails."""

    def __init__(self, session: Session):
        self._session = session

    def get(self, delivery_id: str) -> CandidateEmailDelivery:
        entity = self._session.get(CandidateEmailDelivery, delivery_id)
        if entity is None:
            raise ResourceNotFoundError(f"Candidate email delivery '{delivery_id}' was not found")
        return entity

    def list_pending(self, *, limit: int = 100) -> list[CandidateEmailDelivery]:
        stmt = (
            select(CandidateEmailDelivery)
            .where(CandidateEmailDelivery.status.in_(("pending", "failed")))
            .order_by(CandidateEmailDelivery.updated_at.asc())
            .limit(max(1, limit))
        )
        return list(self._session.execute(stmt).scalars().all())

    def list_by_job(self, *, job_id: str, candidate_id: str | None = None, limit: int = 100) -> list[CandidateEmailDelivery]:
        stmt = select(CandidateEmailDelivery).where(CandidateEmailDelivery.job_id == job_id)
        if candidate_id is not None:
            stmt = stmt.where(CandidateEmailDelivery.candidate_id == candidate_id)
        stmt = stmt.order_by(CandidateEmailDelivery.created_at.desc()).limit(max(1, limit))
        return list(self._session.execute(stmt).scalars().all())

    def create(
        self,
        *,
        candidate_id: str,
        job_id: str,
        template_code: str,
        to_email: str,
        subject: str,
        scene: str = "interview_invitation",
        evaluation_id: str | None = None,
        invitation_id: str | None = None,
        cc_emails: list[str] | None = None,
        bcc_emails: list[str] | None = None,
        html_body: str | None = None,
        text_body: str | None = None,
        provider: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> CandidateEmailDelivery:
        self._assert_relations(
            candidate_id=candidate_id,
            job_id=job_id,
            evaluation_id=evaluation_id,
            invitation_id=invitation_id,
        )
        entity = CandidateEmailDelivery(
            candidate_id=candidate_id,
            job_id=job_id,
            evaluation_id=evaluation_id,
            invitation_id=invitation_id,
            template_code=template_code,
            scene=scene,
            to_email=to_email,
            cc_emails=cc_emails,
            bcc_emails=bcc_emails,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            provider=provider,
            payload=payload,
        )
        self._session.add(entity)
        self._session.flush()
        return entity

    def mark_sent(
        self,
        delivery_id: str,
        *,
        provider: str,
        provider_message_id: str | None,
    ) -> CandidateEmailDelivery:
        entity = self.get(delivery_id)
        entity.status = "sent"
        entity.provider = provider
        entity.provider_message_id = provider_message_id
        entity.sent_at = datetime.now(UTC).replace(tzinfo=None)
        entity.last_error = None
        self._session.flush()
        return entity

    def mark_sending(self, delivery_id: str) -> CandidateEmailDelivery:
        entity = self.get(delivery_id)
        entity.status = "sending"
        entity.last_error = None
        self._session.flush()
        return entity

    def mark_failed(self, delivery_id: str, *, error_message: str) -> CandidateEmailDelivery:
        entity = self.get(delivery_id)
        entity.status = "failed"
        entity.retry_count += 1
        entity.last_error = error_message
        self._session.flush()
        return entity

    def mark_event(self, delivery_id: str, *, status: str) -> CandidateEmailDelivery:
        entity = self.get(delivery_id)
        now = datetime.now(UTC).replace(tzinfo=None)
        entity.status = status
        if status == "delivered":
            entity.delivered_at = now
        elif status == "opened":
            entity.opened_at = now
        elif status == "clicked":
            entity.clicked_at = now
        self._session.flush()
        return entity

    def _assert_relations(
        self,
        *,
        candidate_id: str,
        job_id: str,
        evaluation_id: str | None,
        invitation_id: str | None,
    ) -> None:
        if self._session.get(Candidate, candidate_id) is None:
            raise ResourceNotFoundError(f"Candidate '{candidate_id}' was not found")
        if self._session.get(Job, job_id) is None:
            raise ResourceNotFoundError(f"Job '{job_id}' was not found")
        if evaluation_id:
            evaluation = self._session.get(CandidateJobEvaluation, evaluation_id)
            if evaluation is None or evaluation.candidate_id != candidate_id or evaluation.job_id != job_id:
                raise ResourceNotFoundError(f"Evaluation '{evaluation_id}' was not found for candidate/job pair")
        if invitation_id:
            invitation = self._session.get(AIInterviewInvitation, invitation_id)
            if invitation is None or invitation.candidate_id != candidate_id or invitation.job_id != job_id:
                raise ResourceNotFoundError(f"Invitation '{invitation_id}' was not found for candidate/job pair")
