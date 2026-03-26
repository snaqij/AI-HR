"""漏斗指标仓储实现。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import Approval, Candidate, Interview, Job


class MetricsRepository:
    """提供招聘漏斗聚合所需的数据查询。"""

    def __init__(self, session: Session):
        self._session = session

    def get_funnel_counts(self) -> dict[str, int]:
        """返回最小可运行漏斗阶段计数。"""
        jobs = int(self._session.execute(select(func.count(Job.id))).scalar_one() or 0)
        candidates = int(self._session.execute(select(func.count(Candidate.id))).scalar_one() or 0)
        interviews = int(self._session.execute(select(func.count(Interview.id))).scalar_one() or 0)
        offer_approved = int(
            self._session.execute(
                select(func.count(Approval.id)).where(
                    Approval.action_type == "offer",
                    Approval.status == "approved",
                )
            ).scalar_one()
            or 0
        )
        return {
            "jobs": jobs,
            "candidates": candidates,
            "interviews": interviews,
            "offer_approved": offer_approved,
        }

