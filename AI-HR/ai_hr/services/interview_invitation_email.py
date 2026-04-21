"""Interview invitation email delivery services."""

from __future__ import annotations

import re
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from string import Template
from typing import Any

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.exceptions import InvalidStateError, ResourceNotFoundError
from ..repositories.ai_interviews import AIInterviewInvitationRepository, AIInterviewSessionRepository
from ..repositories.automation_task_logs import AutomationTaskLogRepository
from ..repositories.candidate_email_deliveries import CandidateEmailDeliveryRepository
from ..repositories.candidate_job_evaluations import CandidateJobEvaluationRepository
from ..repositories.candidate_job_pipeline import CandidateJobPipelineRepository
from ..repositories.candidates import CandidateRepository
from ..repositories.email_templates import EmailTemplateRepository
from ..repositories.jobs import JobRepository
from .ai_interviews import get_ai_interview_service
from ..schemas.interview_invitation_email import (
    CandidateEmailDeliveryListResult,
    CandidateEmailDeliveryResponse,
    InterviewAIAnalysis,
    InterviewInvitationHistoryItem,
    InterviewInvitationHistoryResult,
    InterviewInvitationRecordDetailResult,
    InterviewQuestionAnswerItem,
)


@dataclass(slots=True)
class _RenderedInvitationEmail:
    subject: str
    html_body: str | None
    text_body: str
    to_email: str
    invitation_link: str


class InterviewInvitationEmailService:
    """Creates interview invitations and sends email to qualified candidates."""

    _MANUAL_INVITE_MIN_SCORE = 75.0

    def __init__(self, session: Session):
        self._session = session
        self._settings = get_settings()
        self._candidate_repository = CandidateRepository(session)
        self._job_repository = JobRepository(session)
        self._pipeline_repository = CandidateJobPipelineRepository(session)
        self._evaluation_repository = CandidateJobEvaluationRepository(session)
        self._email_delivery_repository = CandidateEmailDeliveryRepository(session)
        self._email_template_repository = EmailTemplateRepository(session)
        self._invitation_repository = AIInterviewInvitationRepository(session)
        self._interview_session_repository = AIInterviewSessionRepository(session)
        self._automation_log_repository = AutomationTaskLogRepository(session)

    def invite_candidate_for_evaluation(
        self,
        *,
        evaluation_id: str,
        template_code: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        evaluation = self._evaluation_repository.get(evaluation_id)
        candidate = self._candidate_repository.get(evaluation.candidate_id)
        job = self._job_repository.get(evaluation.job_id)
        pipeline = self._pipeline_repository.get_by_candidate_job(candidate_id=candidate.id, job_id=job.id)
        if pipeline is None:
            raise InvalidStateError(f"Candidate '{candidate.id}' has no pipeline under job '{job.id}'")
        if evaluation.recommendation not in {"recommend", "strong_recommend"} and float(evaluation.final_score or 0.0) < self._MANUAL_INVITE_MIN_SCORE:
            raise InvalidStateError(
                f"Candidate '{candidate.id}' is not eligible for invitation with recommendation '{evaluation.recommendation}' and score '{evaluation.final_score}'"
            )

        candidate_email = self._resolve_candidate_email(candidate.raw_profile or {}, candidate.email)
        if not candidate_email:
            raise InvalidStateError(f"Candidate '{candidate.id}' has no email address for invitation delivery")

        # 1. 幂等性检查：防止重复发送
        existing_delivery = self._email_delivery_repository.list_by_job(
            job_id=job.id,
            candidate_id=candidate.id,
            limit=1
        )
        if existing_delivery and any(d.status in {"sent", "delivered"} for d in existing_delivery):
             # 如果该候选人在该岗位下已经成功发送过邀请，则跳过
             return {
                "candidate_id": candidate.id,
                "job_id": job.id,
                "status": "skipped",
                "reason": "already_sent",
            }

        task_log = self._automation_log_repository.create(
            task_type="candidate_invitation_email_send",
            task_name="candidate_invitation_email_send",
            status="running",
            trigger_mode="manual",
            entity_type="candidate_job_evaluation",
            entity_id=evaluation.id,
            candidate_id=candidate.id,
            job_id=job.id,
            request_payload={"template_code": template_code or self._settings.ai_auto_invitation_template_code},
        )
        try:
            # 默认优先使用高端版模板
            target_template_code = template_code or "interview_invitation_premium"
            
            ai_interview_service = get_ai_interview_service(self._session)
            invitation = ai_interview_service.create_invitation(candidate_id=candidate.id, job_id=job.id, note=note)
            rendered = self._render_email(
                candidate_name=candidate.name,
                candidate_email=candidate_email,
                job_title=job.title,
                invitation_token=invitation.token,
                expires_at=invitation.expires_at,
                template_code=target_template_code,
            )
            delivery = self._email_delivery_repository.create(
                candidate_id=candidate.id,
                job_id=job.id,
                evaluation_id=evaluation.id,
                invitation_id=invitation.id,
                template_code=target_template_code,
                to_email=rendered.to_email,
                subject=rendered.subject,
                html_body=rendered.html_body,
                text_body=rendered.text_body,
                provider="smtp",
                payload={"invitation_link": rendered.invitation_link},
            )
            self._session.commit()

            self._email_delivery_repository.mark_sending(delivery.id)
            self._session.commit()
            
            try:
                provider_message_id = self._send_via_smtp(rendered=rendered)
                self._email_delivery_repository.mark_sent(
                    delivery.id,
                    provider="smtp",
                    provider_message_id=provider_message_id,
                )
                self._invitation_repository.update_delivery(
                    invitation.id,
                    email_delivery_id=delivery.id,
                    invitation_channel="email",
                    payload_patch={"invitation_link": rendered.invitation_link},
                )
                self._pipeline_repository.mark_invited(
                    pipeline.id,
                    invitation_id=invitation.id,
                    payload_patch={"last_delivery_id": delivery.id},
                )
                self._evaluation_repository.mark_invited(evaluation.id, invited=True)
                self._automation_log_repository.mark_succeeded(
                    task_log.id,
                    result_payload={"delivery_id": delivery.id, "invitation_id": invitation.id},
                )
            except Exception as smtp_exc:
                self._email_delivery_repository.mark_failed(delivery.id, error_message=str(smtp_exc))
                raise smtp_exc
                
            self._session.commit()
            return {
                "candidate_id": candidate.id,
                "job_id": job.id,
                "evaluation_id": evaluation.id,
                "delivery_id": delivery.id,
                "invitation_id": invitation.id,
                "to_email": rendered.to_email,
                "status": "sent",
                "invitation_link": rendered.invitation_link,
            }
        except Exception as exc:
            self._pipeline_repository.mark_failed(pipeline.id, stage="invitation", reason=str(exc))
            self._automation_log_repository.mark_failed(task_log.id, error_message=str(exc))
            self._session.commit()
            raise

    def invite_due_candidates(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        if not self._settings.ai_auto_invitation_enabled:
            return []
        due_pipelines = self._pipeline_repository.list_by_status(
            evaluation_status="completed",
            invitation_status="not_invited",
            limit=limit or self._settings.ai_auto_invitation_batch_size,
        )
        results: list[dict[str, Any]] = []
        for pipeline in due_pipelines:
            if not pipeline.latest_evaluation_id:
                continue
            try:
                results.append(self.invite_candidate_for_evaluation(evaluation_id=pipeline.latest_evaluation_id))
            except Exception as exc:  # noqa: BLE001
                results.append(
                    {
                        "candidate_id": pipeline.candidate_id,
                        "job_id": pipeline.job_id,
                        "status": "failed",
                        "error_message": str(exc),
                    }
                )
        return results

    def send_manual_invitation(
        self,
        *,
        job_id: str,
        candidate_id: str,
        evaluation_id: str | None = None,
        template_code: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        self._job_repository.get(job_id)
        self._candidate_repository.get(candidate_id)
        evaluation = (
            self._evaluation_repository.get(evaluation_id)
            if evaluation_id
            else self._evaluation_repository.get_latest_by_candidate_job(candidate_id=candidate_id, job_id=job_id)
        )
        if evaluation is None:
            raise ResourceNotFoundError(f"No evaluation found for candidate '{candidate_id}' under job '{job_id}'")
        if evaluation.job_id != job_id or evaluation.candidate_id != candidate_id:
            raise InvalidStateError("Evaluation does not belong to the specified candidate/job pair")
        return self.invite_candidate_for_evaluation(
            evaluation_id=evaluation.id,
            template_code=template_code,
            note=note,
        )

    def list_job_email_deliveries(
        self,
        *,
        job_id: str,
        candidate_id: str | None = None,
        limit: int = 100,
    ) -> CandidateEmailDeliveryListResult:
        self._job_repository.get(job_id)
        items = self._email_delivery_repository.list_by_job(job_id=job_id, candidate_id=candidate_id, limit=limit)
        return CandidateEmailDeliveryListResult(
            job_id=job_id,
            total=len(items),
            items=[self._to_delivery_response(item) for item in items],
        )

    def list_invitation_history(
        self,
        *,
        limit: int = 200,
        keyword: str | None = None,
        status: str | None = None,
    ) -> InterviewInvitationHistoryResult:
        rows = self._email_delivery_repository.list_history(
            limit=limit,
            keyword=keyword,
            status=status,
        )
        return InterviewInvitationHistoryResult(
            total=len(rows),
            items=[
                InterviewInvitationHistoryItem(
                    id=delivery.id,
                    candidate_id=candidate.id,
                    candidate_name=candidate.name,
                    candidate_email=candidate.email,
                    job_id=job.id,
                    job_title=job.title,
                    delivery_status=delivery.status,
                    scene=delivery.scene,
                    sent_at=delivery.sent_at,
                    created_at=delivery.created_at,
                    updated_at=delivery.updated_at,
                )
                for delivery, candidate, job in rows
            ],
        )

    def get_invitation_record_detail(self, *, delivery_id: str) -> InterviewInvitationRecordDetailResult:
        """Get interview record detail for one invitation delivery."""
        delivery = self._email_delivery_repository.get(delivery_id)
        if delivery.scene != "interview_invitation":
            raise InvalidStateError(f"Delivery '{delivery_id}' is not an interview invitation record")

        candidate = self._candidate_repository.get(delivery.candidate_id)
        job = self._job_repository.get(delivery.job_id)
        detail = InterviewInvitationRecordDetailResult(
            delivery_id=delivery.id,
            candidate_id=candidate.id,
            candidate_name=candidate.name,
            candidate_email=candidate.email,
            job_id=job.id,
            job_title=job.title,
            delivery_status=delivery.status,
            invitation_id=delivery.invitation_id,
        )
        if not delivery.invitation_id:
            detail.record_message = "该邀请记录尚未关联面试邀请。"
            return detail

        invitation = self._invitation_repository.get_by_id(delivery.invitation_id)
        question_set = self._interview_session_repository.get_latest_question_set(invitation_id=invitation.id)

        session_id = question_set.session_id if question_set and question_set.session_id else None
        if session_id is None:
            detail.record_message = "候选人尚未开始面试。"
            detail.questions = self._build_question_answers(
                questions=question_set.questions_json if question_set else [],
                candidate_turns=[],
            )
            return detail

        detail.session_id = session_id
        turns = self._interview_session_repository.list_turns(session_id)
        candidate_turns = [
            turn
            for turn in turns
            if str(turn.speaker).lower() == "candidate" and (turn.transcript or "").strip()
        ]
        report = self._interview_session_repository.get_latest_report(session_id)

        detail.questions = self._build_question_answers(
            questions=question_set.questions_json if question_set else [],
            candidate_turns=candidate_turns,
        )
        detail.analysis = InterviewAIAnalysis(
            summary=report.summary if report else None,
            recommendation=report.recommendation if report else None,
            dimension_scores=dict(report.dimension_scores_json or {}) if report else {},
            risk_tags=list(report.risk_tags_json or []) if report else [],
        )
        detail.has_record = bool(detail.questions or candidate_turns or report)
        if not detail.has_record:
            detail.record_message = "暂无面试记录。"
        return detail

    def _build_question_answers(self, *, questions: list[dict[str, Any]], candidate_turns: list[Any]) -> list[InterviewQuestionAnswerItem]:
        question_items: list[InterviewQuestionAnswerItem] = []
        for index, raw_question in enumerate(questions, start=1):
            question_id = str(
                raw_question.get("id")
                or raw_question.get("question_id")
                or raw_question.get("idx")
                or index
            ).strip()
            question_text = str(
                raw_question.get("question")
                or raw_question.get("text")
                or raw_question.get("title")
                or raw_question.get("prompt")
                or ""
            ).strip()
            if not question_text:
                continue
            turn = candidate_turns[index - 1] if index - 1 < len(candidate_turns) else None
            question_items.append(
                InterviewQuestionAnswerItem(
                    question_id=question_id or str(index),
                    question=question_text,
                    candidate_answer=(turn.transcript or "").strip() if turn else None,
                    answer_turn_no=int(turn.turn_no) if turn else None,
                )
            )
        if question_items:
            return question_items

        return [
            InterviewQuestionAnswerItem(
                question_id=f"candidate-turn-{idx + 1}",
                question=f"候选人作答片段 {idx + 1}",
                candidate_answer=(turn.transcript or "").strip(),
                answer_turn_no=int(turn.turn_no),
            )
            for idx, turn in enumerate(candidate_turns)
        ]

    def _render_email(
        self,
        *,
        candidate_name: str,
        candidate_email: str,
        job_title: str,
        invitation_token: str,
        expires_at,
        template_code: str,
    ) -> _RenderedInvitationEmail:
        invitation_link = self._build_invitation_link(invitation_token)
        template = self._get_template(template_code)
        context = {
            "candidate_name": candidate_name,
            "job_title": job_title,
            "interview_link": invitation_link,
            "expire_at": expires_at.isoformat(sep=" ", timespec="seconds"),
            "contact_email": self._settings.email_from_address or "",
        }
        subject = self._render_template(template["subject_template"], context)
        html_body = self._render_template(template["html_template"], context) if template.get("html_template") else None
        text_body = self._render_template(template["text_template"], context)
        return _RenderedInvitationEmail(
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            to_email=candidate_email,
            invitation_link=invitation_link,
        )

    def _get_template(self, template_code: str) -> dict[str, str | None]:
        try:
            entity = self._email_template_repository.get_by_code(template_code)
            return {
                "subject_template": entity.subject_template,
                "html_template": entity.html_template,
                "text_template": entity.text_template or entity.subject_template,
            }
        except ResourceNotFoundError:
            return {
                "subject_template": "【面试邀请】诚邀您参加${job_title}岗位面试",
                "html_template": (
                    "<p>${candidate_name}，您好：</p>"
                    "<p>感谢您关注 ${job_title} 岗位。结合您的简历评估结果，我们诚邀您进入面试环节。</p>"
                    "<p>请点击以下链接开始面试：<a href=\"${interview_link}\">${interview_link}</a></p>"
                    "<p>链接有效期至：${expire_at}</p>"
                    "<p>如有问题，请联系：${contact_email}</p>"
                ),
                "text_template": (
                    "${candidate_name}，您好：\n"
                    "感谢您关注${job_title}岗位。结合您的简历评估结果，我们诚邀您进入面试环节。\n"
                    "请通过以下链接开始面试：${interview_link}\n"
                    "链接有效期至：${expire_at}\n"
                    "如有问题，请联系：${contact_email}"
                ),
            }

    def _render_template(self, template_text: str | None, context: dict[str, str]) -> str:
        template_text = (template_text or "").replace("{{", "${").replace("}}", "}")
        return Template(template_text).safe_substitute(context).strip()

    def _build_invitation_link(self, token: str) -> str:
        base_url = self._settings.interview_invitation_base_url.strip()
        if "{token}" in base_url:
            return base_url.format(token=token)
        return f"{base_url.rstrip('/')}/{token}"

    def _send_via_smtp(self, *, rendered: _RenderedInvitationEmail) -> str:
        if not self._settings.email_from_address:
            raise InvalidStateError("SMTP sender address is not configured")
        if not self._settings.email_smtp_host:
            raise InvalidStateError("SMTP host is not configured")

        message = EmailMessage()
        from_name = self._settings.email_from_name.strip()
        message["From"] = f"{from_name} <{self._settings.email_from_address}>"
        message["To"] = rendered.to_email
        message["Subject"] = rendered.subject
        message.set_content(rendered.text_body)
        if rendered.html_body:
            message.add_alternative(rendered.html_body, subtype="html")

        if self._settings.email_smtp_use_ssl:
            smtp = smtplib.SMTP_SSL(self._settings.email_smtp_host, self._settings.email_smtp_port, timeout=20)
        else:
            smtp = smtplib.SMTP(self._settings.email_smtp_host, self._settings.email_smtp_port, timeout=20)
        with smtp:
            if self._settings.email_smtp_use_tls and not self._settings.email_smtp_use_ssl:
                smtp.starttls()
            if self._settings.email_smtp_username:
                smtp.login(
                    self._settings.email_smtp_username,
                    self._settings.email_smtp_password or "",
                )
            smtp.send_message(message)
        return f"smtp:{rendered.to_email}:{int(hash(rendered.subject))}"

    def _resolve_candidate_email(self, raw_profile: dict[str, Any], direct_email: str | None) -> str | None:
        if direct_email and self._looks_like_email(direct_email):
            return direct_email.strip()
        for key in ("email", "mail", "contact_email"):
            value = raw_profile.get(key)
            if isinstance(value, str) and self._looks_like_email(value):
                return value.strip()
        return None

    def _looks_like_email(self, value: str) -> bool:
        """校验邮箱格式。"""
        if not value:
            return False
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return bool(re.match(pattern, value.strip()))

    def _to_delivery_response(self, entity) -> CandidateEmailDeliveryResponse:
        return CandidateEmailDeliveryResponse(
            id=entity.id,
            candidate_id=entity.candidate_id,
            job_id=entity.job_id,
            evaluation_id=entity.evaluation_id,
            invitation_id=entity.invitation_id,
            template_code=entity.template_code,
            scene=entity.scene,
            to_email=entity.to_email,
            subject=entity.subject,
            provider=entity.provider,
            provider_message_id=entity.provider_message_id,
            status=entity.status,
            retry_count=entity.retry_count,
            max_retry_count=entity.max_retry_count,
            last_error=entity.last_error,
            sent_at=entity.sent_at,
            delivered_at=entity.delivered_at,
            opened_at=entity.opened_at,
            clicked_at=entity.clicked_at,
            payload=entity.payload,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )


def get_interview_invitation_email_service(session: Session) -> InterviewInvitationEmailService:
    """Return an invitation email service bound to the current session."""

    return InterviewInvitationEmailService(session)
