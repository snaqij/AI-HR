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
    InterviewOpeningSegmentItem,
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
        
        # Score/recommendation limits are intentionally removed to allow manual invitations for any candidate.
        # if evaluation.recommendation not in {"recommend", "strong_recommend"} and float(evaluation.final_score or 0.0) < self._MANUAL_INVITE_MIN_SCORE:
        #     raise InvalidStateError(
        #         f"Candidate '{candidate.id}' is not eligible for invitation with recommendation '{evaluation.recommendation}' and score '{evaluation.final_score}'"
        #     )

        candidate_email = self._resolve_candidate_email(candidate.raw_profile or {}, candidate.email)
        if not candidate_email:
            raise InvalidStateError(f"Candidate '{candidate.id}' has no email address for invitation delivery")

        # 1) Idempotency check: avoid sending duplicate invitation emails
        existing_delivery = self._email_delivery_repository.list_by_job(
            job_id=job.id,
            candidate_id=candidate.id,
            limit=1
        )
        if existing_delivery and any(d.status in {"sent", "delivered"} for d in existing_delivery):
            raise InvalidStateError("该候选人已发送过面试邀请，请勿重复发送")

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
                    workspace_id=delivery.workspace_id,
                    created_by_user_id=delivery.created_by_user_id,
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
            workspace_id=delivery.workspace_id,
            created_by_user_id=delivery.created_by_user_id,
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
        raw_questions = question_set.questions_json if question_set and question_set.questions_json else []
        questions_payload = raw_questions if isinstance(raw_questions, list) else []
        opening_from_questions, remaining_questions = self._split_opening_questions(questions_payload)

        session_id = question_set.session_id if question_set and question_set.session_id else None
        if session_id is None:
            detail.record_message = "候选人尚未开始面试。"
            detail.opening_segments = opening_from_questions
            detail.questions = self._build_question_answers(
                questions=remaining_questions,
                turns_by_question_id={},
                anonymous_question_groups=[],
                unassigned_turns=[],
                followups_by_question_id={},
            )
            return detail

        detail.session_id = session_id
        turns = self._interview_session_repository.list_turns(session_id)
        bindings = self._bind_turns_to_question_context(turns=turns, questions=remaining_questions)
        candidate_turns = list(bindings.get("candidate_turns", []))
        report = self._interview_session_repository.get_latest_report(session_id)
        opening_by_stage = dict(bindings.get("opening_by_stage", {}) or {})
        detail.opening_segments = self._build_opening_segments_from_bindings(
            opening_from_questions=opening_from_questions,
            opening_by_stage=opening_by_stage,
            opening_followups=list(bindings.get("opening_followups", []) or []),
        )

        detail.questions = self._build_question_answers(
            questions=remaining_questions,
            turns_by_question_id=dict(bindings.get("turns_by_question_id", {}) or {}),
            anonymous_question_groups=list(bindings.get("anonymous_question_groups", []) or []),
            unassigned_turns=list(bindings.get("unassigned_turns", []) or []),
            followups_by_question_id=dict(bindings.get("followups_by_question_id", {}) or {}),
        )
        detail.analysis = InterviewAIAnalysis(
            summary=report.summary if report else None,
            recommendation=report.recommendation if report else None,
            dimension_scores=dict(report.dimension_scores_json or {}) if report else {},
            risk_tags=list(report.risk_tags_json or []) if report else [],
        )
        detail.has_record = bool(detail.opening_segments or detail.questions or candidate_turns or report)
        if not detail.has_record:
            detail.record_message = "暂无面试记录。"
        return detail

    def _build_opening_segments_from_bindings(
        self,
        *,
        opening_from_questions: list[InterviewOpeningSegmentItem],
        opening_by_stage: dict[str, list[Any]],
        opening_followups: list[str],
    ) -> list[InterviewOpeningSegmentItem]:
        segments: list[InterviewOpeningSegmentItem] = []
        dedup_followups: list[str] = []
        for followup in list(opening_followups or []):
            text = str(followup or "").strip()
            if not text or text in dedup_followups:
                continue
            dedup_followups.append(text)
        for segment in opening_from_questions:
            title = str(segment.title or "").strip()
            if title != "自我介绍":
                continue
            # Product decision: remove standalone "项目介绍" section and merge its follow-ups into 自我介绍.
            grouped_turns = list((opening_by_stage or {}).get("S1", []) or [])
            grouped_turns.extend(list((opening_by_stage or {}).get("S2", []) or []))
            grouped_turns.sort(key=lambda item: int(getattr(item, "turn_no", 0) or 0))
            if grouped_turns:
                merged_answer = self._merge_turn_texts(grouped_turns)
                segments.append(
                    InterviewOpeningSegmentItem(
                        title=title or segment.title,
                        followup_questions=dedup_followups,
                        candidate_answer=merged_answer,
                        answer_turn_no=int(grouped_turns[0].turn_no),
                    )
                )
            else:
                segments.append(
                    InterviewOpeningSegmentItem(
                        title=title or segment.title,
                        followup_questions=dedup_followups,
                        candidate_answer=segment.candidate_answer,
                        answer_turn_no=segment.answer_turn_no,
                    )
                )
        return segments

    def _split_opening_questions(
        self, questions: list[dict[str, Any]]
    ) -> tuple[list[InterviewOpeningSegmentItem], list[dict[str, Any]]]:
        opening: list[InterviewOpeningSegmentItem] = []
        opening_indexes: set[int] = set()

        def _normalize_stage(raw: Any) -> str:
            return str(raw or "").strip().upper()

        def _is_self_intro_prompt(text: str) -> bool:
            normalized = text.strip()
            if not normalized:
                return False
            return bool(
                re.search(r"自我介绍|介绍一下你自己|先做.{0,8}自我介绍", normalized)
            )

        def _is_project_intro_prompt(text: str) -> bool:
            normalized = text.strip()
            if not normalized:
                return False
            return bool(
                re.search(r"项目介绍|介绍一下.{0,8}项目|先讲.{0,8}项目|先介绍.{0,8}项目", normalized)
            )

        for idx, item in enumerate(questions):
            stage = _normalize_stage(item.get("stage") or item.get("stage_code"))
            text = str(
                item.get("question")
                or item.get("text")
                or item.get("title")
                or item.get("prompt")
                or ""
            ).strip()
            if not text:
                continue
            if stage == "S1" and not any(seg.title == "自我介绍" for seg in opening):
                opening.append(InterviewOpeningSegmentItem(title="自我介绍", candidate_answer=None, answer_turn_no=None))
                opening_indexes.add(idx)
                continue
            if stage == "S2":
                # Remove standalone 项目介绍 section; keep S2 prompts out of formal question list.
                opening_indexes.add(idx)
                continue

        if not any(seg.title == "自我介绍" for seg in opening):
            for idx, item in enumerate(questions):
                text = str(item.get("question") or item.get("text") or item.get("title") or item.get("prompt") or "").strip()
                if _is_self_intro_prompt(text):
                    opening.append(InterviewOpeningSegmentItem(title="自我介绍", candidate_answer=None, answer_turn_no=None))
                    opening_indexes.add(idx)
                    break

        for idx, item in enumerate(questions):
            text = str(item.get("question") or item.get("text") or item.get("title") or item.get("prompt") or "").strip()
            if _is_project_intro_prompt(text):
                # Remove project-intro prompt from formal question list and fold it into 自我介绍阶段.
                opening_indexes.add(idx)

        # Ensure opening sections are always visible in UI even when question pack
        # does not explicitly include S1/opening-style prompts.
        if not any(seg.title == "自我介绍" for seg in opening):
            opening.append(InterviewOpeningSegmentItem(title="自我介绍", candidate_answer=None, answer_turn_no=None))

        opening = [seg for seg in opening if seg.title == "自我介绍"]
        remaining = [item for idx, item in enumerate(questions) if idx not in opening_indexes]
        return opening, remaining

    def _build_question_answers(
        self,
        *,
        questions: list[dict[str, Any]],
        turns_by_question_id: dict[str, list[Any]],
        anonymous_question_groups: list[list[Any]],
        unassigned_turns: list[Any],
        followups_by_question_id: dict[str, list[str]],
    ) -> list[InterviewQuestionAnswerItem]:
        def _normalize_question_identifier(raw: Any) -> str:
            return str(raw or "").strip()

        question_items: list[InterviewQuestionAnswerItem] = []
        for index, raw_question in enumerate(questions, start=1):
            question_id = _normalize_question_identifier(
                raw_question.get("id")
                or raw_question.get("question_id")
                or raw_question.get("idx")
                or index
            )
            question_text = str(
                raw_question.get("question")
                or raw_question.get("text")
                or raw_question.get("title")
                or raw_question.get("prompt")
                or ""
            ).strip()
            if not question_text:
                continue
            followups = [
                str(item or "").strip()
                for item in list((followups_by_question_id or {}).get(question_id, []) or [])
                if str(item or "").strip()
            ]
            dedup_followups: list[str] = []
            for followup in followups:
                if followup == question_text or followup in dedup_followups:
                    continue
                dedup_followups.append(followup)
            matched_turns = list(turns_by_question_id.get(question_id, []))
            answer_text = self._merge_turn_texts(matched_turns) if matched_turns else None
            answer_turn_no = int(matched_turns[0].turn_no) if matched_turns else None
            question_items.append(
                InterviewQuestionAnswerItem(
                    question_id=question_id or str(index),
                    question=question_text,
                    followup_questions=dedup_followups,
                    candidate_answer=answer_text,
                    answer_turn_no=answer_turn_no,
                )
            )
        if question_items:
            return question_items

        # Fallback only when there is no question-pack at all.
        candidate_turns: list[Any] = []
        seen_turn_nos: set[int] = set()
        for grouped in list((turns_by_question_id or {}).values()) + list(anonymous_question_groups or []) + [[t] for t in (unassigned_turns or [])]:
            for turn in grouped or []:
                turn_no = int(getattr(turn, "turn_no", 0) or 0)
                if turn_no <= 0 or turn_no in seen_turn_nos:
                    continue
                seen_turn_nos.add(turn_no)
                candidate_turns.append(turn)
        candidate_turns.sort(key=lambda item: int(getattr(item, "turn_no", 0) or 0))
        return [
            InterviewQuestionAnswerItem(
                question_id=f"candidate-turn-{idx + 1}",
                question=f"候选人作答片段 {idx + 1}",
                candidate_answer=(turn.transcript or "").strip(),
                answer_turn_no=int(turn.turn_no),
            )
            for idx, turn in enumerate(candidate_turns)
        ]

    def _merge_turn_texts(self, turns: list[Any]) -> str | None:
        merged_parts: list[str] = []
        for turn in turns:
            text = str(turn.transcript or "").strip()
            if not text:
                continue
            if merged_parts and merged_parts[-1] == text:
                continue
            merged_parts.append(text)
        merged = " ".join(merged_parts).strip()
        return merged or None

    def _extract_turn_question_id(self, turn: Any) -> str:
        payload = dict(getattr(turn, "payload", {}) or {})
        return str(getattr(turn, "question_id", None) or payload.get("question_id") or "").strip()

    def _extract_turn_stage(self, turn: Any) -> str:
        payload = dict(getattr(turn, "payload", {}) or {})
        return str(payload.get("stage") or payload.get("interview_stage") or "").strip().upper()

    def _bind_turns_to_question_context(self, *, turns: list[Any], questions: list[dict[str, Any]]) -> dict[str, Any]:
        question_ids = {
            str(item.get("id") or item.get("question_id") or "").strip()
            for item in questions
            if isinstance(item, dict)
        }
        question_ids.discard("")
        question_id_by_seq: dict[int, str] = {}
        for index, item in enumerate(list(questions or []), start=1):
            if not isinstance(item, dict):
                continue
            qid = str(item.get("id") or item.get("question_id") or "").strip()
            if not qid:
                continue
            raw_seq = item.get("question_seq")
            if raw_seq is None:
                raw_seq = item.get("idx")
            try:
                seq = int(raw_seq) if raw_seq is not None else index
            except (TypeError, ValueError):
                seq = index
            if seq > 0 and seq not in question_id_by_seq:
                question_id_by_seq[seq] = qid

        opening_by_stage: dict[str, list[Any]] = {"S1": []}
        turns_by_question_id: dict[str, list[Any]] = {}
        followups_by_question_id: dict[str, list[str]] = {}
        opening_followups: list[str] = []
        anonymous_question_groups: list[list[Any]] = []
        unassigned_turns: list[Any] = []
        candidate_turns: list[Any] = []

        sorted_turns = sorted(list(turns or []), key=lambda item: int(getattr(item, "turn_no", 0) or 0))
        opening_root_seen = False
        formal_started = False

        for turn in sorted_turns:
            payload = dict(getattr(turn, "payload", {}) or {})
            speaker = str(getattr(turn, "speaker", "") or "").strip().lower()
            transcript = str(getattr(turn, "transcript", "") or "").strip()
            if not transcript:
                continue

            phase = str(payload.get("phase") or "").strip().lower()
            stage = self._extract_turn_stage(turn)
            raw_qid = self._extract_turn_question_id(turn)
            qid = raw_qid if raw_qid in question_ids else ""
            raw_seq = payload.get("question_seq")
            if raw_seq is None:
                raw_seq = getattr(turn, "question_seq", None)
            try:
                qseq = int(raw_seq) if raw_seq is not None else None
            except (TypeError, ValueError):
                qseq = None
            if not qid and qseq is not None:
                qid = str(question_id_by_seq.get(qseq) or "").strip()
            is_followup = bool(payload.get("is_followup", False))
            event_type = str(payload.get("original_event_type") or "").strip().lower()

            is_opening = bool(
                phase == "opening"
                or stage in ("S1", "S2", "OPENING", "SELF_INTRO")
                or (not phase and not qid and not formal_started and speaker == "ai")
            )
            is_formal = bool(
                phase == "formal"
                or bool(qid)
                or (qseq is not None and qseq in question_id_by_seq)
            )

            if speaker == "ai":
                if event_type == "question.final":
                    if is_opening and not is_formal:
                        if opening_root_seen:
                            opening_followups.append(transcript)
                        else:
                            opening_root_seen = True
                    elif is_formal and qid:
                        formal_started = True
                        if is_followup:
                            followups_by_question_id.setdefault(qid, []).append(transcript)
                continue

            if speaker != "candidate":
                continue

            candidate_turns.append(turn)
            if is_opening and not is_formal:
                opening_by_stage.setdefault("S1", []).append(turn)
                continue
            if is_formal and qid:
                turns_by_question_id.setdefault(qid, []).append(turn)
                continue
            unassigned_turns.append(turn)

        return {
            "candidate_turns": candidate_turns,
            "opening_by_stage": opening_by_stage,
            "opening_followups": opening_followups,
            "turns_by_question_id": turns_by_question_id,
            "followups_by_question_id": followups_by_question_id,
            "anonymous_question_groups": anonymous_question_groups,
            "unassigned_turns": unassigned_turns,
        }

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
                "subject_template": "【面试邀请】诚邀您参加 ${job_title} 岗位面试",
                "html_template": (
                    "<p>${candidate_name}，您好：</p>"
                    "<p>感谢您关注 ${job_title} 岗位。结合您的简历评估结果，我们诚邀您进入面试环节。</p>"
                    "<p>请点击以下链接开始面试：<a href=\"${interview_link}\">${interview_link}</a></p>"
                    "<p>链接有效期至：${expire_at}</p>"
                    "<p>如有问题，请联系：${contact_email}</p>"
                ),
                "text_template": (
                    "${candidate_name}，您好：\n"
                    "感谢您关注 ${job_title} 岗位。结合您的简历评估结果，我们诚邀您进入面试环节。\n"
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

        smtp_host = self._settings.email_smtp_host
        smtp_port = self._settings.email_smtp_port
        try:
            if self._settings.email_smtp_use_ssl:
                smtp = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=20)
            else:
                smtp = smtplib.SMTP(smtp_host, smtp_port, timeout=20)
            with smtp:
                if self._settings.email_smtp_use_tls and not self._settings.email_smtp_use_ssl:
                    smtp.starttls()
                if self._settings.email_smtp_username:
                    smtp.login(
                        self._settings.email_smtp_username,
                        self._settings.email_smtp_password or "",
                    )
                smtp.send_message(message)
        except (TimeoutError, OSError, smtplib.SMTPException) as exc:
            raise InvalidStateError(
                f"SMTP connection/send failed: host={smtp_host} port={smtp_port} error={exc}"
            ) from exc
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
        """Validate basic email format."""
        if not value:
            return False
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return bool(re.match(pattern, value.strip()))

    def _to_delivery_response(self, entity) -> CandidateEmailDeliveryResponse:
        return CandidateEmailDeliveryResponse(
            id=entity.id,
            workspace_id=entity.workspace_id,
            created_by_user_id=entity.created_by_user_id,
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


