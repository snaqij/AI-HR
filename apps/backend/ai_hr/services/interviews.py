"""面试排期业务服务。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..connectors.registry import registry
from ..core.config import get_settings
from ..core.exceptions import ConnectorOperationError, InvalidStateError
from ..repositories.candidates import CandidateRepository
from ..repositories.events import EventRepository
from ..repositories.interviews import InterviewRepository
from ..repositories.jobs import JobRepository
from ..schemas.interviews import (
    InterviewDispatchRequest,
    InterviewPlanRequest,
    InterviewScheduleRequest,
    InterviewSendRequest,
    InterviewSyncStatusRequest,
)
from .credentials import get_credential_service, CredentialService


class InterviewService:
    """负责编排面试创建、执行与状态同步。"""

    def __init__(
        self,
        interview_repository: InterviewRepository,
        candidate_repository: CandidateRepository,
        job_repository: JobRepository,
        event_repository: EventRepository,
        credential_service: CredentialService,
    ):
        """注入依赖仓储并读取配置。"""
        self._interview_repository = interview_repository
        self._candidate_repository = candidate_repository
        self._job_repository = job_repository
        self._event_repository = event_repository
        self._credential_service = credential_service
        self._settings = get_settings()

    def schedule_interview(self, payload: InterviewScheduleRequest) -> dict:
        """创建面试排期记录，可选自动执行外部约面。"""
        candidate = self._candidate_repository.get(payload.candidate_id)
        self._job_repository.get(payload.job_id)
        interview = self._interview_repository.create(
            candidate_id=candidate.id,
            job_id=payload.job_id,
            channel=payload.channel,
            scheduled_at=payload.scheduled_at.replace(tzinfo=None) if isinstance(payload.scheduled_at, datetime) else payload.scheduled_at,
            meeting_link=payload.meeting_link,
            target_headcount=payload.target_headcount,
            payload={
                "meeting_provider": payload.meeting_provider,
                "note": payload.note,
                "auto_dispatch": payload.auto_dispatch,
            },
        )
        self._event_repository.create(
            event_type="interview.scheduled",
            entity_type="interview",
            entity_id=interview.id,
            channel=payload.channel,
            payload={"candidate_id": candidate.id, "job_id": payload.job_id},
        )

        dispatch_payload: dict = {}
        dispatched = False
        if payload.auto_dispatch:
            result = self.dispatch_interview(interview.id, InterviewDispatchRequest(force=True))
            interview = result["interview"]
            dispatch_payload = result["dispatch_payload"]
            dispatched = result["status"] == "scheduled"

        return {"interview": interview, "dispatched": dispatched, "dispatch_payload": dispatch_payload}

    def plan_interviews(self, job_id: str, payload: InterviewPlanRequest) -> dict:
        """按岗位 headcount 与 shortlist 生成可发送邀约计划（不超发）。"""
        self._job_repository.get(job_id)
        shortlist = self._interview_repository.list_shortlist(job_id)
        already_planned_or_sent = self._interview_repository.count_distinct_candidates_with_interview(job_id)
        remaining_slots = max(payload.headcount - already_planned_or_sent, 0)
        if remaining_slots == 0:
            return {
                "job_id": job_id,
                "headcount": payload.headcount,
                "already_planned_or_sent": already_planned_or_sent,
                "planned_count": 0,
                "plan": [],
            }

        plan: list[dict] = []
        for shortlist_item in shortlist:
            if len(plan) >= remaining_slots:
                break
            existing = self._interview_repository.find_latest_by_job_candidate(
                job_id=job_id,
                candidate_id=shortlist_item.candidate_id,
            )
            if existing is not None:
                continue
            plan.append(
                {
                    "candidate_id": shortlist_item.candidate_id,
                    "rank": shortlist_item.rank,
                    "reason": "shortlist_rank",
                }
            )

        return {
            "job_id": job_id,
            "headcount": payload.headcount,
            "already_planned_or_sent": already_planned_or_sent,
            "planned_count": len(plan),
            "plan": plan,
        }

    def send_interviews(self, job_id: str, payload: InterviewSendRequest) -> dict:
        """按计划批量创建并可选派发面试邀约，保障同岗位同候选人幂等。"""
        plan = self.plan_interviews(job_id, InterviewPlanRequest(headcount=payload.headcount))
        results: list[dict] = []
        created = 0
        skipped = 0
        sent = 0
        failed = 0

        for item in plan["plan"]:
            candidate_id = item["candidate_id"]
            existing = self._interview_repository.find_latest_by_job_candidate(job_id=job_id, candidate_id=candidate_id)
            if existing is not None:
                skipped += 1
                results.append(
                    {
                        "candidate_id": candidate_id,
                        "status": "skipped",
                        "interview_id": existing.id,
                        "detail": {"reason": "idempotent_existing"},
                    }
                )
                continue

            schedule_result = self.schedule_interview(
                InterviewScheduleRequest(
                    candidate_id=candidate_id,
                    job_id=job_id,
                    channel=payload.channel,
                    scheduled_at=payload.scheduled_at,
                    meeting_link=payload.meeting_link,
                    meeting_provider=payload.meeting_provider,
                    note=payload.note,
                    auto_dispatch=payload.auto_dispatch,
                    target_headcount=payload.headcount,
                )
            )
            created += 1
            interview = schedule_result["interview"]
            dispatch_payload = schedule_result["dispatch_payload"]
            if payload.auto_dispatch:
                if interview.status in {"scheduled", "confirmed"}:
                    sent += 1
                    status = "sent"
                else:
                    failed += 1
                    status = "failed"
            else:
                status = "created"

            results.append(
                {
                    "candidate_id": candidate_id,
                    "status": status,
                    "interview_id": interview.id,
                    "detail": dispatch_payload,
                }
            )

        return {
            "job_id": job_id,
            "headcount": payload.headcount,
            "attempted": len(plan["plan"]),
            "created": created,
            "skipped": skipped,
            "sent": sent,
            "failed": failed,
            "results": results,
        }

    def get_job_interview_progress(self, job_id: str) -> dict:
        """返回岗位维度的面试邀约进度统计。"""
        self._job_repository.get(job_id)
        stats = self._interview_repository.get_progress_stats(job_id)
        return {"job_id": job_id, **stats}

    def dispatch_interview(self, interview_id: str, payload: InterviewDispatchRequest) -> dict:
        """执行 BOSS 约面并回写执行状态。"""
        interview = self._interview_repository.get(interview_id)
        candidate = self._candidate_repository.get(interview.candidate_id)
        if not payload.force and interview.status in {"scheduled", "confirmed"}:
            return {"interview": interview, "status": interview.status, "dispatch_payload": {}}

        connector = self._build_connector(interview.channel)
        slot_payload = {
            "scheduled_at": interview.scheduled_at.isoformat() if interview.scheduled_at else None,
            "meeting_link": interview.meeting_link,
            "meeting_provider": (interview.payload or {}).get("meeting_provider"),
            "note": (interview.payload or {}).get("note"),
        }
        try:
            dispatch = connector.schedule_interview(candidate.external_candidate_id, slot_payload)
            interview = self._interview_repository.update_dispatch_result(
                interview.id,
                status=dispatch.get("status", "scheduled"),
                external_interview_id=dispatch.get("external_interview_id"),
                payload=dispatch,
            )
            self._event_repository.create(
                event_type="interview.dispatch.sent",
                entity_type="interview",
                entity_id=interview.id,
                channel=interview.channel,
                payload={"dispatch": dispatch},
            )
            return {"interview": interview, "status": interview.status, "dispatch_payload": dispatch}
        except ConnectorOperationError as exc:
            interview = self._interview_repository.update_dispatch_result(
                interview.id,
                status="dispatch_failed",
                external_interview_id=interview.external_interview_id,
                payload={"error": str(exc)},
            )
            self._event_repository.create(
                event_type="interview.dispatch.failed",
                entity_type="interview",
                entity_id=interview.id,
                channel=interview.channel,
                status="failed",
                payload={"error": str(exc)},
            )
            return {"interview": interview, "status": interview.status, "dispatch_payload": {"error": str(exc)}}

    def sync_interview_status(self, interview_id: str, payload: InterviewSyncStatusRequest) -> dict:
        """同步 BOSS 约面状态并回写本地记录。"""
        interview = self._interview_repository.get(interview_id)
        if not interview.external_interview_id:
            raise InvalidStateError(f"Interview '{interview_id}' has no external interview id")
        if not payload.force and interview.status in {"cancelled", "rejected"}:
            return {"interview": interview, "status": interview.status, "sync_payload": {}}

        connector = self._build_connector(interview.channel)
        try:
            sync_result = connector.sync_interview_status(interview.external_interview_id)
            interview = self._interview_repository.update_sync_status(
                interview.id,
                status=sync_result.get("status", "unknown"),
                payload=sync_result,
            )
            self._event_repository.create(
                event_type="interview.status.synced",
                entity_type="interview",
                entity_id=interview.id,
                channel=interview.channel,
                payload={"sync": sync_result},
            )
            return {"interview": interview, "status": interview.status, "sync_payload": sync_result}
        except ConnectorOperationError as exc:
            interview = self._interview_repository.update_sync_status(
                interview.id,
                status="sync_failed",
                payload={"error": str(exc)},
            )
            self._event_repository.create(
                event_type="interview.status.sync_failed",
                entity_type="interview",
                entity_id=interview.id,
                channel=interview.channel,
                status="failed",
                payload={"error": str(exc)},
            )
            return {"interview": interview, "status": interview.status, "sync_payload": {"error": str(exc)}}

    def get_interview(self, interview_id: str):
        """查询面试记录。"""
        return self._interview_repository.get(interview_id)

    def _build_connector(self, channel: str):
        """根据渠道构建连接器实例。"""
        if channel == "boss":
            credentials = self._credential_service.resolve_boss_credentials()
            return registry.create(channel, credentials)
        raise ConnectorOperationError(f"Connector '{channel}' is not configured")


def get_interview_service(session: Session) -> InterviewService:
    """返回绑定当前数据库会话的 InterviewService。"""
    return InterviewService(
        interview_repository=InterviewRepository(session),
        candidate_repository=CandidateRepository(session),
        job_repository=JobRepository(session),
        event_repository=EventRepository(session),
        credential_service=get_credential_service(session),
    )
