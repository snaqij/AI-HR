"""AI 批量评分与入围名单仓储实现。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from ..db.models import Candidate, CandidateJobScore, JobShortlist


class AIScoringRepository:
    """封装岗位评分结果与入围名单持久化能力。"""

    def __init__(self, session: Session):
        """使用当前数据库会话初始化仓储。"""
        self._session = session

    def list_candidates(self, candidate_ids: list[str] | None = None) -> list[Candidate]:
        """查询候选人列表；未指定 ID 时返回全部候选人。"""
        stmt = select(Candidate)
        if candidate_ids:
            stmt = stmt.where(Candidate.id.in_(candidate_ids))
        return list(self._session.execute(stmt).scalars().all())

    def upsert_job_score(
        self,
        *,
        candidate_id: str,
        job_id: str,
        total_score: float,
        dimension_scores: dict[str, float],
        explanation: str,
        risk_tags: list[str],
        score_version: str,
    ) -> CandidateJobScore:
        """新增或更新候选人在岗位下的评分结果。"""
        stmt = select(CandidateJobScore).where(
            CandidateJobScore.candidate_id == candidate_id,
            CandidateJobScore.job_id == job_id,
        )
        entity = self._session.execute(stmt).scalar_one_or_none()
        now = datetime.now(UTC).replace(tzinfo=None)
        if entity is None:
            entity = CandidateJobScore(
                candidate_id=candidate_id,
                job_id=job_id,
                total_score=total_score,
                dimension_scores=dimension_scores,
                explanation=explanation,
                risk_tags=risk_tags,
                score_version=score_version,
                scored_at=now,
            )
            self._session.add(entity)
        else:
            entity.total_score = total_score
            entity.dimension_scores = dimension_scores
            entity.explanation = explanation
            entity.risk_tags = risk_tags
            entity.score_version = score_version
            entity.scored_at = now
        self._session.flush()
        return entity

    def list_job_scores(self, job_id: str) -> list[CandidateJobScore]:
        """按岗位查询评分结果。"""
        stmt = (
            select(CandidateJobScore)
            .options(selectinload(CandidateJobScore.candidate))
            .where(CandidateJobScore.job_id == job_id)
        )
        return list(self._session.execute(stmt).scalars().all())

    def replace_shortlist(self, *, job_id: str, candidate_ids: list[str]) -> list[JobShortlist]:
        """按排序结果重建岗位入围名单。"""
        self._session.execute(delete(JobShortlist).where(JobShortlist.job_id == job_id))
        entities: list[JobShortlist] = []
        for index, candidate_id in enumerate(candidate_ids, start=1):
            entity = JobShortlist(
                job_id=job_id,
                candidate_id=candidate_id,
                rank=index,
                status="active",
            )
            self._session.add(entity)
            entities.append(entity)
        self._session.flush()
        return entities

    def list_shortlist(self, job_id: str) -> list[JobShortlist]:
        """按岗位查询入围名单。"""
        stmt = (
            select(JobShortlist)
            .options(selectinload(JobShortlist.candidate))
            .where(JobShortlist.job_id == job_id)
            .order_by(JobShortlist.rank.asc())
        )
        return list(self._session.execute(stmt).scalars().all())

