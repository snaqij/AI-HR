"""岗位仓储实现。"""

from __future__ import annotations

from datetime import datetime, UTC

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..core.exceptions import ResourceNotFoundError
from ..db.models import Job, JobPublication
from ..schemas.jobs import JobCreateRequest, RemoteJobSyncItem


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

    def list_all(self, limit: int = 100, offset: int = 0) -> list[Job]:
        """查询所有岗位记录及关联候选人计数。"""
        from sqlalchemy import func
        from ..db.models import JobCandidate

        # 子查询统计关联候选人数
        count_subq = (
            select(func.count(JobCandidate.id))
            .where(JobCandidate.job_id == Job.id)
            .scalar_subquery()
        )

        stmt = (
            select(Job, count_subq.label("candidate_count"))
            .options(selectinload(Job.publications))
            .order_by(Job.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        results = self._session.execute(stmt).all()
        
        output = []
        for job, count in results:
            # 动态绑定属性，供 Pydantic JobResponse.model_validate 使用
            job.candidate_count = count or 0
            output.append(job)
        return output

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

    def find_publication_by_external_job_id(self, channel: str, external_job_id: str) -> JobPublication | None:
        stmt = select(JobPublication).where(
            JobPublication.channel == channel,
            JobPublication.external_job_id == external_job_id,
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def sync_remote_job(self, channel: str, item: RemoteJobSyncItem) -> tuple[Job, JobPublication, bool]:
        """将渠道侧岗位映射为本地岗位与发布记录。"""
        publication = self.find_publication_by_external_job_id(channel, item.external_job_id)
        created = False
        now = datetime.now(UTC).replace(tzinfo=None)

        if publication is None:
            job = Job(
                title=item.title,
                department=item.department,
                city=item.city,
                salary_range=item.salary,
                requirements=item.requirements or "Imported from remote recruiting channel.",
                status="published" if item.status == "published" else item.status or "imported",
                published_at=now if item.status == "published" else None,
            )
            self._session.add(job)
            self._session.flush()
            publication = JobPublication(
                job_id=job.id,
                channel=channel,
                status=item.status or "published",
                external_job_id=item.external_job_id,
                request_payload={},
                response_payload=item.raw_payload or {},
                published_at=now if item.status == "published" else None,
                last_synced_at=now,
            )
            self._session.add(publication)
            created = True
        else:
            job = publication.job
            job.title = item.title or job.title
            job.department = item.department or job.department
            job.city = item.city or job.city
            job.salary_range = item.salary or job.salary_range
            if item.requirements:
                job.requirements = item.requirements
            if item.status:
                job.status = item.status
            if item.status == "published" and job.published_at is None:
                job.published_at = now
            publication.status = item.status or publication.status
            publication.response_payload = item.raw_payload or {}
            publication.last_synced_at = now
            if publication.published_at is None and item.status == "published":
                publication.published_at = now

        self._session.commit()
        return self.get(job.id), publication, created

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

    def update_settings(
        self,
        job_id: str,
        *,
        auto_request_resume: bool | None = None,
        min_degree: str | None = None,
        min_experience_years: int | None = None,
        max_daily_resume_requests: int | None = None,
    ) -> Job:
        """更新岗位自动化配置。"""
        job = self.get(job_id)
        if auto_request_resume is not None:
            job.auto_request_resume = auto_request_resume
        if min_degree is not None:
            # Normalize or empty string handling
            job.min_degree = min_degree if min_degree and min_degree.strip() else None
        if min_experience_years is not None:
            job.min_experience_years = min_experience_years
        if max_daily_resume_requests is not None:
            job.max_daily_resume_requests = max_daily_resume_requests
            
        self._session.commit()
        self._session.refresh(job)
        return job
