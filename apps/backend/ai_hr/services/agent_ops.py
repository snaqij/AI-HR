"""Service for querying agent run/event observability data."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..repositories.agent_events import AgentEventRepository
from ..repositories.agent_runs import AgentRunRepository
from ..schemas.agent_ops import (
    AgentEventListResult,
    AgentEventResponse,
    AgentRunListResult,
    AgentRunResponse,
)


class AgentOpsService:
    """Aggregates run/event records for operations console APIs."""

    def __init__(self, session: Session):
        self._run_repository = AgentRunRepository(session)
        self._event_repository = AgentEventRepository(session)

    def list_runs(
        self,
        *,
        agent_code: str | None = None,
        task_type: str | None = None,
        status: str | None = None,
        candidate_id: str | None = None,
        job_id: str | None = None,
        limit: int = 100,
    ) -> AgentRunListResult:
        entities = self._run_repository.list(
            agent_code=agent_code,
            task_type=task_type,
            status=status,
            candidate_id=candidate_id,
            job_id=job_id,
            limit=limit,
        )
        return AgentRunListResult(
            total=len(entities),
            items=[AgentRunResponse.model_validate(item) for item in entities],
        )

    def list_events(
        self,
        *,
        run_id: str | None = None,
        agent_code: str | None = None,
        status: str | None = None,
        candidate_id: str | None = None,
        job_id: str | None = None,
        limit: int = 200,
    ) -> AgentEventListResult:
        entities = self._event_repository.list(
            run_id=run_id,
            agent_code=agent_code,
            status=status,
            candidate_id=candidate_id,
            job_id=job_id,
            limit=limit,
        )
        return AgentEventListResult(
            total=len(entities),
            items=[AgentEventResponse.model_validate(item) for item in entities],
        )


def get_agent_ops_service(session: Session) -> AgentOpsService:
    """Return an agent ops service bound to current DB session."""

    return AgentOpsService(session)
