"""Automation orchestration for resume evaluation and invitation delivery."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..repositories.automation_task_logs import AutomationTaskLogRepository
from ..repositories.candidate_job_pipeline import CandidateJobPipelineRepository
from ..schemas.candidate_evaluations import CandidateEvaluationRequest
from .candidate_evaluations import get_candidate_evaluation_service
from .interview_invitation_email import get_interview_invitation_email_service
from ..repositories.candidates import CandidateRepository


class RecruitmentAutomationService:
    """Coordinates evaluation and interview invitation automation."""

    def __init__(self, session: Session):
        self._session = session
        self._settings = get_settings()
        self._pipeline_repository = CandidateJobPipelineRepository(session)
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
            try:
                # 打印评估日志
                candidate = CandidateRepository(self._session).get(pipeline.candidate_id)
                print(f"DEBUG: 开始为候选人 {candidate.name} 进行评估分析")
                
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
                self._automation_log_repository.mark_succeeded(task_log.id, result_payload=result_item)
                self._session.commit()
                results.append(result_item)
            except Exception as exc:  # noqa: BLE001
                self._session.rollback()
                self._pipeline_repository.mark_failed(pipeline.id, stage="evaluation", reason=str(exc))
                self._automation_log_repository.mark_failed(task_log.id, error_message=str(exc))
                self._session.commit()
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
        return self._invitation_email_service.invite_due_candidates(
            limit=limit or self._settings.ai_auto_invitation_batch_size
        )


def get_recruitment_automation_service(session: Session) -> RecruitmentAutomationService:
    """Return a recruitment automation service bound to the current session."""

    return RecruitmentAutomationService(session)
