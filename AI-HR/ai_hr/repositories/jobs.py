"""岗位仓储实现。"""

from __future__ import annotations

from datetime import datetime, UTC

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..core.exceptions import ResourceNotFoundError
from ..db.models import Job, JobPublication
from ..schemas.jobs import JobCreateRequest


class JobRepository:
    """封装岗位及发布记录的持久化操作。"""

    def __init__(self, session: Session):
        """使用当前数据库会话初始化仓储。"""
        self._session = session

    def create(self, payload: JobCreateRequest) -> Job:
        """创建岗位草稿并返回完整实体。"""
        job = Job(
            title=payload.title,
            department=payload.department,
            city=payload.city,
            salary_range=payload.salary_range,
            requirements=payload.requirements,
            status="draft",
        )
        self._session.add(job)
        self._session.commit()
        return self.get(job.id)

    def get(self, job_id: str) -> Job:
        """按岗位 ID 查询岗位及发布记录。"""
        stmt = select(Job).options(selectinload(Job.publications)).where(Job.id == job_id)
        job = self._session.execute(stmt).scalar_one_or_none()
        if job is None:
            raise ResourceNotFoundError(f"Job '{job_id}' was not found")
        return job

    def add_publication(
        self,
        job: Job,
        *,
        channel: str,
        status: str,
        request_payload: dict,
        response_payload: dict,
        external_job_id: str | None = None,
        error_message: str | None = None,
    ) -> JobPublication:
        """新增一条渠道发布记录，并同步岗位发布状态。"""
        now = datetime.now(UTC).replace(tzinfo=None)
        publication = JobPublication(
            job_id=job.id,
            channel=channel,
            status=status,
            external_job_id=external_job_id,
            error_message=error_message,
            request_payload=request_payload,
            response_payload=response_payload,
            published_at=now if status == "published" else None,
            last_synced_at=now,
        )
        self._session.add(publication)
        if status == "published":
            job.status = "published"
            job.published_at = now
        self._session.commit()
        self._session.refresh(publication)
        return publication

    def list_publications(self, job_id: str) -> list[JobPublication]:
        """返回岗位关联的全部发布记录。"""
        job = self.get(job_id)
        return list(job.publications)

    def update_publication_sync_result(
        self,
        publication_id: str,
        *,
        status: str,
        response_payload: dict,
        error_message: str | None = None,
    ) -> JobPublication:
        """更新发布同步结果（状态、返回体、错误信息）。"""
        stmt = select(JobPublication).where(JobPublication.id == publication_id)
        publication = self._session.execute(stmt).scalar_one_or_none()
        if publication is None:
            raise ResourceNotFoundError(f"Job publication '{publication_id}' was not found")

        now = datetime.now(UTC).replace(tzinfo=None)
        publication.status = status
        publication.response_payload = response_payload
        publication.error_message = error_message
        publication.last_synced_at = now
        if status == "published" and publication.published_at is None:
            publication.published_at = now
        self._session.commit()
        self._session.refresh(publication)
        return publication

    def update_publication_cursor(self, publication_id: str, cursor: str | None) -> JobPublication:
        """更新候选人同步游标。"""
        stmt = select(JobPublication).where(JobPublication.id == publication_id)
        publication = self._session.execute(stmt).scalar_one_or_none()
        if publication is None:
            raise ResourceNotFoundError(f"Job publication '{publication_id}' was not found")

        publication.applicant_sync_cursor = cursor
        publication.last_synced_at = datetime.now(UTC).replace(tzinfo=None)
        self._session.commit()
        self._session.refresh(publication)
        return publication
