"""Agent operations query APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...core.responses import Envelope
from ...db.session import get_db_session
from ...schemas.agent_ops import AgentEventListResult, AgentRunListResult
from ...services.agent_ops import get_agent_ops_service

router = APIRouter(prefix="/agent", tags=["agent-ops"])


@router.get("/runs", response_model=Envelope[AgentRunListResult])
def list_agent_runs(
    agent_code: str | None = Query(default=None),
    task_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    candidate_id: str | None = Query(default=None),
    job_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=300),
    session: Session = Depends(get_db_session),
) -> Envelope[AgentRunListResult]:
    service = get_agent_ops_service(session)
    result = service.list_runs(
        agent_code=agent_code,
        task_type=task_type,
        status=status,
        candidate_id=candidate_id,
        job_id=job_id,
        limit=limit,
    )
    return Envelope.success(result)


@router.get("/events", response_model=Envelope[AgentEventListResult])
def list_agent_events(
    run_id: str | None = Query(default=None),
    agent_code: str | None = Query(default=None),
    status: str | None = Query(default=None),
    candidate_id: str | None = Query(default=None),
    job_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> Envelope[AgentEventListResult]:
    service = get_agent_ops_service(session)
    result = service.list_events(
        run_id=run_id,
        agent_code=agent_code,
        status=status,
        candidate_id=candidate_id,
        job_id=job_id,
        limit=limit,
    )
    return Envelope.success(result)
