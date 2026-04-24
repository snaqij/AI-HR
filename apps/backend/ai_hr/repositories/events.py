"""事件仓储实现。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from ..db.models import Event


class EventRepository:
    """封装事件写入能力，用于审计与追踪。"""

    def __init__(self, session: Session):
        """使用当前数据库会话初始化仓储。"""
        self._session = session

    def create(
        self,
        *,
        event_type: str,
        entity_type: str,
        entity_id: str,
        status: str = "success",
        channel: str | None = None,
        operator: str | None = None,
        session_id: str | None = None,
        job_id: str | None = None,
        payload: dict | None = None,
    ) -> Event:
        """创建事件记录并返回持久化实体。"""
        event = Event(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            status=status,
            channel=channel,
            operator=operator,
            session_id=session_id,
            job_id=job_id,
            payload=payload or {},
        )
        self._session.add(event)
        self._session.commit()
        self._session.refresh(event)
        return event

    def query(
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
    ) -> tuple[int, list[Event]]:
        """按条件查询审计事件。"""
        filters = []
        if event_type:
            filters.append(Event.event_type == event_type)
        if entity_type:
            filters.append(Event.entity_type == entity_type)
        if entity_id:
            filters.append(Event.entity_id == entity_id)
        if status:
            filters.append(Event.status == status)
        if operator:
            filters.append(Event.operator == operator)
        if session_id:
            filters.append(Event.session_id == session_id)
        if job_id:
            filters.append(Event.job_id == job_id)
        if occurred_from:
            filters.append(Event.occurred_at >= occurred_from)
        if occurred_to:
            filters.append(Event.occurred_at <= occurred_to)

        stmt = select(Event)
        if filters:
            stmt = stmt.where(and_(*filters))

        # Minimal implementation: derive total from result length; can be replaced by COUNT query later.
        items = list(
            self._session.execute(stmt.order_by(Event.occurred_at.desc()).limit(max(1, min(limit, 200)))).scalars().all()
        )
        return len(items), items
