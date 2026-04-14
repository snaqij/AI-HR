"""Repository for job-candidate links."""

from __future__ import annotations

import base64
from datetime import UTC, datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, load_only, selectinload

from ..core.exceptions import InvalidStateError
from ..db.models import Candidate, CandidateJobPipeline, JobCandidate


class JobCandidateRepository:
    """Handles upsert and query operations for job-candidate links."""

    def __init__(self, session: Session):
        self._session = session

    def upsert_link(
        self,
        *,
        job_id: str,
        publication_id: str | None,
        candidate_id: str,
        channel: str,
        external_job_id: str | None,
        external_candidate_id: str,
        stage: str,
        source_status: str | None,
        applied_at: datetime | None,
        source_payload: dict,
    ) -> JobCandidate:
        stmt = select(JobCandidate).where(
            JobCandidate.job_id == job_id,
            JobCandidate.channel == channel,
            JobCandidate.external_candidate_id == external_candidate_id,
        )
        entity = self._session.execute(stmt).scalar_one_or_none()
        now = datetime.now(UTC).replace(tzinfo=None)

        if entity is None:
            entity = JobCandidate(
                job_id=job_id,
                publication_id=publication_id,
                candidate_id=candidate_id,
                channel=channel,
                external_job_id=external_job_id,
                external_candidate_id=external_candidate_id,
                stage=stage,
                source_status=source_status,
                applied_at=applied_at,
                first_synced_at=now,
                last_synced_at=now,
                source_payload=source_payload or {},
            )
            self._session.add(entity)
            return entity

        entity.publication_id = publication_id
        entity.candidate_id = candidate_id
        entity.external_job_id = external_job_id
        entity.stage = stage
        entity.source_status = source_status
        entity.applied_at = applied_at
        entity.last_synced_at = now
        entity.source_payload = source_payload or {}
        return entity

    def list_by_job(
        self,
        job_id: str,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[list[JobCandidate], str | None, bool]:
        page_size = max(1, min(limit, 200))
        stmt = (
            select(JobCandidate)
            .options(
                load_only(
                    JobCandidate.id,
                    JobCandidate.candidate_id,
                    JobCandidate.job_id,
                    JobCandidate.channel,
                    JobCandidate.external_candidate_id,
                    JobCandidate.external_job_id,
                    JobCandidate.stage,
                    JobCandidate.source_status,
                    JobCandidate.first_synced_at,
                    JobCandidate.last_synced_at,
                ),
                selectinload(JobCandidate.candidate).load_only(
                    Candidate.id,
                    Candidate.name,
                    Candidate.email,
                    Candidate.current_stage,
                    Candidate.school,
                    Candidate.degree,
                    Candidate.work_experience,
                    Candidate.expected_salary,
                    Candidate.latest_company,
                    Candidate.created_at,
                    Candidate.updated_at,
                ),
                selectinload(JobCandidate.pipeline).load_only(
                    CandidateJobPipeline.resume_request_status,
                    CandidateJobPipeline.resume_download_status,
                    CandidateJobPipeline.last_resume_requested_at,
                ),
            )
            .options(
                selectinload(JobCandidate.evaluation),
                selectinload(JobCandidate.latest_delivery),
            )
            .where(JobCandidate.job_id == job_id)
            .order_by(JobCandidate.last_synced_at.desc(), JobCandidate.id.desc())
        )

        if cursor:
            cursor_time, cursor_id = self._decode_cursor(cursor)
            stmt = stmt.where(
                or_(
                    JobCandidate.last_synced_at < cursor_time,
                    and_(JobCandidate.last_synced_at == cursor_time, JobCandidate.id < cursor_id),
                )
            )

        rows = list(self._session.execute(stmt.limit(page_size + 1)).scalars().all())
        has_more = len(rows) > page_size
        items = rows[:page_size]
        next_cursor = self._encode_cursor(items[-1]) if has_more and items else None
        return items, next_cursor, has_more

    def list_by_candidate(self, candidate_id: str) -> list[JobCandidate]:
        stmt = (
            select(JobCandidate)
            .options(selectinload(JobCandidate.candidate))
            .where(JobCandidate.candidate_id == candidate_id)
            .order_by(JobCandidate.last_synced_at.desc())
        )
        return list(self._session.execute(stmt).scalars().all())

    def get_link(self, job_id: str, candidate_id: str) -> JobCandidate | None:
        stmt = select(JobCandidate).where(
            JobCandidate.job_id == job_id,
            JobCandidate.candidate_id == candidate_id,
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def get_link_detail(self, job_id: str, candidate_id: str) -> JobCandidate | None:
        stmt = (
            select(JobCandidate)
            .options(
                load_only(
                    JobCandidate.id,
                    JobCandidate.candidate_id,
                    JobCandidate.job_id,
                    JobCandidate.channel,
                    JobCandidate.external_candidate_id,
                    JobCandidate.external_job_id,
                    JobCandidate.stage,
                    JobCandidate.source_status,
                    JobCandidate.applied_at,
                    JobCandidate.first_synced_at,
                    JobCandidate.last_synced_at,
                ),
                selectinload(JobCandidate.candidate).load_only(
                    Candidate.id,
                    Candidate.name,
                    Candidate.email,
                    Candidate.current_stage,
                    Candidate.school,
                    Candidate.degree,
                    Candidate.work_experience,
                    Candidate.expected_salary,
                    Candidate.latest_company,
                    Candidate.created_at,
                    Candidate.updated_at,
                ),
                selectinload(JobCandidate.pipeline).load_only(
                    CandidateJobPipeline.resume_request_status,
                    CandidateJobPipeline.resume_download_status,
                    CandidateJobPipeline.last_resume_requested_at,
                ),
            )
            .options(
                selectinload(JobCandidate.evaluation),
                selectinload(JobCandidate.latest_delivery),
            )
            .where(JobCandidate.job_id == job_id, JobCandidate.candidate_id == candidate_id)
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def update_stage(self, entity: JobCandidate, stage: str) -> JobCandidate:
        entity.stage = stage
        entity.updated_at = datetime.now(UTC).replace(tzinfo=None)
        self._session.commit()
        return entity

    def count_by_stage(self) -> dict[str, int]:
        from sqlalchemy import func

        stmt = select(JobCandidate.stage, func.count(JobCandidate.id)).group_by(JobCandidate.stage)
        results = self._session.execute(stmt).all()
        return {stage: count for stage, count in results}

    def get_total_synced_count(self) -> int:
        from sqlalchemy import func

        stmt = select(func.count(JobCandidate.id))
        return self._session.execute(stmt).scalar() or 0

    def count_by_job(self, job_id: str) -> int:
        from sqlalchemy import func

        stmt = select(func.count(JobCandidate.id)).where(JobCandidate.job_id == job_id)
        return self._session.execute(stmt).scalar() or 0

    def get_job_stats(self, job_id: str) -> dict[str, int]:
        """返回岗位的聚合统计数据。一次性查询总数、评估数和发信数。"""
        from sqlalchemy import func
        from ..db.models import CandidateJobEvaluation, CandidateEmailDelivery

        # 使用标量子查询合并计数，减少数据库交互次数
        total_subq = (
            select(func.count(JobCandidate.id))
            .where(JobCandidate.job_id == job_id)
            .scalar_subquery()
        )

        evaluated_subq = (
            select(func.count(func.distinct(CandidateJobEvaluation.candidate_id)))
            .where(CandidateJobEvaluation.job_id == job_id)
            .scalar_subquery()
        )

        sent_subq = (
            select(func.count(func.distinct(CandidateEmailDelivery.candidate_id)))
            .where(
                CandidateEmailDelivery.job_id == job_id,
                CandidateEmailDelivery.status == "sent"
            )
            .scalar_subquery()
        )

        stmt = select(
            total_subq.label("total"),
            evaluated_subq.label("evaluated"),
            sent_subq.label("sent")
        )
        
        result = self._session.execute(stmt).one()

        return {
            "total": result.total or 0,
            "evaluated": result.evaluated or 0,
            "sent": result.sent or 0,
        }

    def _encode_cursor(self, item: JobCandidate) -> str:
        payload = f"{item.last_synced_at.isoformat()}|{item.id}"
        return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("utf-8")

    def _decode_cursor(self, cursor: str) -> tuple[datetime, str]:
        try:
            decoded = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
            ts, item_id = decoded.split("|", 1)
            return datetime.fromisoformat(ts), item_id
        except Exception as exc:  # noqa: BLE001
            raise InvalidStateError("Invalid candidates cursor") from exc
