"""治理能力路由：审批、审计、漏斗指标。"""

from __future__ import annotations
from datetime import datetime
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from ...core.responses import Envelope
from ...db.session import get_db_session
from ...schemas.governance import (
    ApprovalCreateRequest,
    ApprovalDecisionRequest,
    ApprovalResponse,
    AuditEventQueryResult,
    FunnelMetricsResult,
)
from ...services.governance import get_governance_service

router = APIRouter(prefix="", tags=["governance"])


@router.post("/approvals", response_model=Envelope[ApprovalResponse], status_code=status.HTTP_201_CREATED)
def create_approval(
    payload: ApprovalCreateRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[ApprovalResponse]:
    """创建审批申请。"""
    service = get_governance_service(session)
    approval = service.create_approval(payload)
    return Envelope.success(ApprovalResponse.model_validate(approval))


@router.post("/approvals/{approval_id}/decision", response_model=Envelope[ApprovalResponse])
def decide_approval(
    approval_id: str,
    payload: ApprovalDecisionRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[ApprovalResponse]:
    """提交审批结论。"""
    service = get_governance_service(session)
    approval = service.decide_approval(approval_id, payload)
    return Envelope.success(ApprovalResponse.model_validate(approval))


@router.get("/audit/events", response_model=Envelope[AuditEventQueryResult])
def query_audit_events(
    event_type: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    operator: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
    job_id: str | None = Query(default=None),
    occurred_from: datetime | None = Query(default=None),
    occurred_to: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_db_session),
) -> Envelope[AuditEventQueryResult]:
    """查询审计事件，支持动作/实体/时间过滤。"""
    service = get_governance_service(session)
    result = service.query_audit_events(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        status=status_filter,
        operator=operator,
        session_id=session_id,
        job_id=job_id,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        limit=limit,
    )
    return Envelope.success(result)


@router.get("/metrics/funnel", response_model=Envelope[FunnelMetricsResult])
def get_funnel_metrics(
    session: Session = Depends(get_db_session),
) -> Envelope[FunnelMetricsResult]:
    """查询招聘漏斗阶段指标与转化率。"""
    service = get_governance_service(session)
    result = service.get_funnel_metrics()
    return Envelope.success(result)
