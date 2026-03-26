"""审批、审计与漏斗指标服务。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..repositories.approvals import ApprovalRepository
from ..repositories.events import EventRepository
from ..repositories.metrics import MetricsRepository
from ..schemas.governance import (
    ApprovalCreateRequest,
    ApprovalDecisionRequest,
    AuditEventQueryResult,
    FunnelMetricsResult,
    FunnelStageItem,
)


class GovernanceService:
    """聚合治理相关业务能力。"""

    def __init__(self, session: Session):
        self._approval_repository = ApprovalRepository(session)
        self._event_repository = EventRepository(session)
        self._metrics_repository = MetricsRepository(session)

    def create_approval(self, payload: ApprovalCreateRequest):
        """创建审批申请并写入审计事件。"""
        approval = self._approval_repository.create(
            action_type=payload.action_type,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            requested_by=payload.requested_by,
            reason=payload.reason,
            payload=payload.payload,
        )
        self._event_repository.create(
            event_type="approval.created",
            entity_type="approval",
            entity_id=approval.id,
            status="success",
            operator=payload.requested_by,
            payload={"action_type": payload.action_type, "entity_type": payload.entity_type, "entity_id": payload.entity_id},
        )
        return approval

    def decide_approval(self, approval_id: str, payload: ApprovalDecisionRequest):
        """提交审批结论并写入审计事件。"""
        approval = self._approval_repository.decide(
            approval_id,
            decision=payload.decision,
            decided_by=payload.decided_by,
            note=payload.note,
        )
        self._event_repository.create(
            event_type=f"approval.{payload.decision}",
            entity_type="approval",
            entity_id=approval.id,
            status="success",
            operator=payload.decided_by,
            payload={"decided_by": payload.decided_by, "note": payload.note},
        )
        return approval

    def query_audit_events(
        self,
        *,
        event_type: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        status: str | None = None,
        operator: str | None = None,
        session_id: str | None = None,
        job_id: str | None = None,
        occurred_from: datetime | None = None,
        occurred_to: datetime | None = None,
        limit: int = 50,
    ) -> AuditEventQueryResult:
        """查询审计事件。"""
        total, items = self._event_repository.query(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            status=status,
            operator=operator,
            session_id=session_id,
            job_id=job_id,
            occurred_from=occurred_from,
            occurred_to=occurred_to,
            limit=limit,
        )
        return AuditEventQueryResult(total=total, items=items)

    def get_funnel_metrics(self) -> FunnelMetricsResult:
        """返回最小可运行漏斗指标。"""
        counts = self._metrics_repository.get_funnel_counts()
        jobs = counts["jobs"]
        candidates = counts["candidates"]
        interviews = counts["interviews"]
        offer_approved = counts["offer_approved"]

        def _rate(numerator: int, denominator: int) -> float | None:
            if denominator <= 0:
                return None
            return round(numerator / denominator, 4)

        stages = [
            FunnelStageItem(stage="jobs", count=jobs),
            FunnelStageItem(stage="candidates", count=candidates, conversion_rate=_rate(candidates, jobs)),
            FunnelStageItem(stage="interviews", count=interviews, conversion_rate=_rate(interviews, candidates)),
            FunnelStageItem(stage="offer_approved", count=offer_approved, conversion_rate=_rate(offer_approved, interviews)),
        ]
        return FunnelMetricsResult(stages=stages)


def get_governance_service(session: Session) -> GovernanceService:
    """返回绑定数据库会话的治理服务。"""
    return GovernanceService(session)
