"""审批仓储实现。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.exceptions import ResourceNotFoundError
from ..db.models import Approval


class ApprovalRepository:
    """封装审批记录的持久化能力。"""

    def __init__(self, session: Session):
        self._session = session

    def create(
        self,
        *,
        action_type: str,
        entity_type: str,
        entity_id: str,
        requested_by: str,
        reason: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Approval:
        """创建待审批记录。"""
        approval = Approval(
            action_type=action_type,
            entity_type=entity_type,
            entity_id=entity_id,
            requested_by=requested_by,
            reason=reason,
            payload=payload or {},
            status="pending",
        )
        self._session.add(approval)
        self._session.commit()
        self._session.refresh(approval)
        return approval

    def get(self, approval_id: str) -> Approval:
        """按 ID 查询审批记录。"""
        stmt = select(Approval).where(Approval.id == approval_id)
        approval = self._session.execute(stmt).scalar_one_or_none()
        if approval is None:
            raise ResourceNotFoundError(f"Approval '{approval_id}' was not found")
        return approval

    def decide(self, approval_id: str, *, decision: str, decided_by: str, note: str | None = None) -> Approval:
        """更新审批结果。"""
        approval = self.get(approval_id)
        approval.status = decision
        approval.decided_by = decided_by
        approval.decided_at = datetime.now(UTC).replace(tzinfo=None)

        merged_payload = dict(approval.payload or {})
        if note:
            merged_payload["decision_note"] = note
        approval.payload = merged_payload
        self._session.commit()
        self._session.refresh(approval)
        return approval

