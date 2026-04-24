"""AI 离线评测仓储。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..db.models import AIEvalRun


class AIEvalRepository:
    """封装离线评测运行记录的读写。"""

    def __init__(self, session: Session):
        self._session = session

    def create_run(
        self,
        *,
        eval_type: str,
        dataset_version: str,
        model_version: str,
        metrics: dict[str, Any],
        status: str = "completed",
        started_at: datetime,
        finished_at: datetime,
    ) -> AIEvalRun:
        """创建一条评测运行记录。"""
        entity = AIEvalRun(
            eval_type=eval_type,
            dataset_version=dataset_version,
            model_version=model_version,
            metrics=metrics,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
        )
        self._session.add(entity)
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def get_run(self, run_id: str) -> AIEvalRun | None:
        """按运行 ID 查询评测记录。"""
        stmt = select(AIEvalRun).where(AIEvalRun.id == run_id)
        return self._session.execute(stmt).scalar_one_or_none()

    def get_latest_run(self, eval_type: str) -> AIEvalRun | None:
        """按评测类型查询最近一次运行。"""
        stmt = select(AIEvalRun).where(AIEvalRun.eval_type == eval_type).order_by(desc(AIEvalRun.finished_at))
        return self._session.execute(stmt).scalars().first()
