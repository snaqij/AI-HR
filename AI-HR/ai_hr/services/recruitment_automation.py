"""Automation orchestration for resume evaluation and invitation delivery."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..repositories.agent_events import AgentEventRepository
from ..repositories.agent_runs import AgentRunRepository
from ..repositories.automation_task_logs import AutomationTaskLogRepository
from ..repositories.candidate_job_pipeline import CandidateJobPipelineRepository
from ..repositories.candidates import CandidateRepository
from ..schemas.candidate_evaluations import CandidateEvaluationRequest
from .candidate_evaluations import get_candidate_evaluation_service
from .interview_invitation_email import get_interview_invitation_email_service

logger = logging.getLogger(__name__)


class RecruitmentAutomationService:
    """Coordinates evaluation and interview invitation automation."""

    def __init__(self, session: Session):
        self._session = session
        self._settings = get_settings()
        self._pipeline_repository = CandidateJobPipelineRepository(session)
        self._agent_run_repository = AgentRunRepository(session)
        self._agent_event_repository = AgentEventRepository(session)
        self._automation_log_repository = AutomationTaskLogRepository(session)
        self._candidate_evaluation_service = get_candidate_evaluation_service(session)
        self._invitation_email_service = get_interview_invitation_email_service(session)

    def execute_due_candidate_evaluations(self, *, limit: int | None = None) -> list[dict]:
        pipelines = self._pipeline_repository.list_by_status(
            resume_download_status="downloaded",
            evaluation_status="pending",
            limit=limit or self._settings.ai_candidate_evaluation_batch_size,
        )
        results: list[dict] = []
        for pipeline in pipelines:
            agent_run = self._agent_run_repository.create(
                agent_code="candidate_evaluator",
                agent_type="worker",
                task_type="candidate_evaluation",
                status="running",
                trigger_mode="scheduler",
                entity_type="candidate_job_pipeline",
                entity_id=pipeline.id,
                candidate_id=pipeline.candidate_id,
                job_id=pipeline.job_id,
                request_payload={"evaluation_version": "v1"},
            )
            self._agent_event_repository.create(
                run_id=agent_run.id,
                agent_code="candidate_evaluator",
                event_type="run",
                event_name="run.started",
                status="running",
                message="Candidate evaluation run started.",
                entity_type="candidate_job_pipeline",
                entity_id=pipeline.id,
                candidate_id=pipeline.candidate_id,
                job_id=pipeline.job_id,
                payload={"evaluation_version": "v1"},
            )
            task_log = self._automation_log_repository.create(
                task_type="candidate_evaluation",
                task_name="candidate_evaluation",
                status="running",
                trigger_mode="scheduler",
                entity_type="candidate_job_pipeline",
                entity_id=pipeline.id,
                candidate_id=pipeline.candidate_id,
                job_id=pipeline.job_id,
            )
            self._session.commit()
            try:
                candidate = CandidateRepository(self._session).get(pipeline.candidate_id)
                logger.info(
                    "recruitment_automation.evaluate.start trace_id=%s candidate_id=%s job_id=%s candidate_name=%s",
                    agent_run.id,
                    pipeline.candidate_id,
                    pipeline.job_id,
                    candidate.name,
                )

                detail = self._candidate_evaluation_service.evaluate_candidate(
                    job_id=pipeline.job_id,
                    candidate_id=pipeline.candidate_id,
                    payload=CandidateEvaluationRequest(evaluation_version="v1", force_refresh=False),
                )
                result_item = {
                    "candidate_id": pipeline.candidate_id,
                    "job_id": pipeline.job_id,
                    "evaluation_id": detail.evaluation.id,
                    "final_score": detail.evaluation.final_score,
                    "recommendation": detail.evaluation.recommendation,
                    "status": "completed",
                }
                self._agent_event_repository.create(
                    run_id=agent_run.id,
                    agent_code="candidate_evaluator",
                    event_type="evaluation",
                    event_name="evaluation.completed",
                    status="success",
                    message="Candidate evaluation completed.",
                    entity_type="candidate_job_pipeline",
                    entity_id=pipeline.id,
                    candidate_id=pipeline.candidate_id,
                    job_id=pipeline.job_id,
                    payload={
                        "evaluation_id": detail.evaluation.id,
                        "final_score": detail.evaluation.final_score,
                        "recommendation": detail.evaluation.recommendation,
                    },
                )
                self._agent_run_repository.mark_succeeded(agent_run.id, result_payload=result_item)
                self._automation_log_repository.mark_succeeded(task_log.id, result_payload=result_item)
                self._session.commit()
                logger.info(
                    "recruitment_automation.evaluate.success trace_id=%s candidate_id=%s job_id=%s evaluation_id=%s final_score=%s recommendation=%s",
                    agent_run.id,
                    pipeline.candidate_id,
                    pipeline.job_id,
                    detail.evaluation.id,
                    detail.evaluation.final_score,
                    detail.evaluation.recommendation,
                )
                results.append(result_item)
            except Exception as exc:  # noqa: BLE001
                self._session.rollback()
                self._pipeline_repository.mark_failed(pipeline.id, stage="evaluation", reason=str(exc))
                self._automation_log_repository.mark_failed(task_log.id, error_message=str(exc))
                self._agent_event_repository.create(
                    run_id=agent_run.id,
                    agent_code="candidate_evaluator",
                    event_type="evaluation",
                    event_name="evaluation.failed",
                    status="failed",
                    message="Candidate evaluation failed.",
                    entity_type="candidate_job_pipeline",
                    entity_id=pipeline.id,
                    candidate_id=pipeline.candidate_id,
                    job_id=pipeline.job_id,
                    payload={"error_message": str(exc)},
                )
                self._agent_run_repository.mark_failed(agent_run.id, error_message=str(exc))
                self._session.commit()
                logger.exception(
                    "recruitment_automation.evaluate.failed trace_id=%s candidate_id=%s job_id=%s",
                    agent_run.id,
                    pipeline.candidate_id,
                    pipeline.job_id,
                )
                results.append(
                    {
                        "candidate_id": pipeline.candidate_id,
                        "job_id": pipeline.job_id,
                        "status": "failed",
                        "error_message": str(exc),
                    }
                )
        return results

    def execute_due_invitation_emails(self, *, limit: int | None = None) -> list[dict]:
        batch_limit = limit or self._settings.ai_auto_invitation_batch_size
        agent_run = self._agent_run_repository.create(
            agent_code="invitation_dispatcher",
            agent_type="worker",
            task_type="candidate_invitation_dispatch",
            status="running",
            trigger_mode="scheduler",
            request_payload={"limit": batch_limit},
        )
        self._agent_event_repository.create(
            run_id=agent_run.id,
            agent_code="invitation_dispatcher",
            event_type="run",
            event_name="run.started",
            status="running",
            message="Invitation dispatch run started.",
            payload={"limit": batch_limit},
        )
        self._session.commit()
        logger.info(
            "recruitment_automation.invitation_dispatch.start trace_id=%s limit=%s",
            agent_run.id,
            batch_limit,
        )
        try:
            results = self._invitation_email_service.invite_due_candidates(limit=batch_limit)
            self._agent_event_repository.create(
                run_id=agent_run.id,
                agent_code="invitation_dispatcher",
                event_type="invitation",
                event_name="invitation.batch.completed",
                status="success",
                message="Invitation dispatch run completed.",
                payload={
                    "total": len(results),
                    "sent": len([item for item in results if item.get("status") == "sent"]),
                    "failed": len([item for item in results if item.get("status") == "failed"]),
                },
            )
            self._agent_run_repository.mark_succeeded(
                agent_run.id,
                result_payload={
                    "total": len(results),
                    "sent": len([item for item in results if item.get("status") == "sent"]),
                    "failed": len([item for item in results if item.get("status") == "failed"]),
                },
            )
            self._session.commit()
            logger.info(
                "recruitment_automation.invitation_dispatch.success trace_id=%s total=%s sent=%s failed=%s",
                agent_run.id,
                len(results),
                len([item for item in results if item.get("status") == "sent"]),
                len([item for item in results if item.get("status") == "failed"]),
            )
            return results
        except Exception as exc:  # noqa: BLE001
            self._session.rollback()
            self._agent_event_repository.create(
                run_id=agent_run.id,
                agent_code="invitation_dispatcher",
                event_type="invitation",
                event_name="invitation.batch.failed",
                status="failed",
                message="Invitation dispatch run failed.",
                payload={"error_message": str(exc)},
            )
            self._agent_run_repository.mark_failed(agent_run.id, error_message=str(exc))
            self._session.commit()
            logger.exception("recruitment_automation.invitation_dispatch.failed trace_id=%s", agent_run.id)
            raise


def get_recruitment_automation_service(session: Session) -> RecruitmentAutomationService:
    """Return a recruitment automation service bound to the current session."""

    return RecruitmentAutomationService(session)
