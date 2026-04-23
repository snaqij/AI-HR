"""岗位仓储实现。"""

from __future__ import annotations

from datetime import datetime, UTC

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from ..core.exceptions import ResourceNotFoundError
from ..db.models import Job, JobPublication
from ..schemas.jobs import JobCreateRequest, RemoteJobSyncItem
from .workspace_scope import get_workspace_id


class JobRepository:
    """封装岗位及发布记录的持久化操作。"""

    def __init__(self, session: Session):
        """使用当前数据库会话初始化仓储。"""
        self._session = session

    def create(self, payload: JobCreateRequest) -> Job:
        """创建岗位草稿并返回完整实体。"""
        workspace_id = get_workspace_id(self._session)
        job = Job(
            workspace_id=workspace_id,
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
        workspace_id = get_workspace_id(self._session)
        if workspace_id:
            stmt = stmt.where(Job.workspace_id == workspace_id)
        job = self._session.execute(stmt).scalar_one_or_none()
        if job is None:
            raise ResourceNotFoundError(f"Job '{job_id}' was not found")
        return job

    def list_all(
        self,
        limit: int = 100,
        offset: int = 0,
        *,
        platform: str | None = None,
        name: str | None = None,
        job_type: str | None = None,
        salary: str | None = None,
    ) -> list[Job]:
        """查询所有岗位记录及关联候选人计数。"""
        from sqlalchemy import func
        from ..db.models import JobCandidate

        # Subquery to count related candidates
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
        workspace_id = get_workspace_id(self._session)
        if workspace_id:
            stmt = stmt.where(Job.workspace_id == workspace_id)
        results = self._session.execute(stmt).all()
        
        output = []
        for job, count in results:
            # Dynamically bind attributes for Pydantic JobResponse.model_validate
            job.candidate_count = count or 0
            output.append(job)
        return self._filter_jobs(
            output,
            platform=platform,
            name=name,
            job_type=job_type,
            salary=salary,
        )

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
        workspace_id = get_workspace_id(self._session)
        if workspace_id:
            stmt = stmt.join(Job, Job.id == JobPublication.job_id).where(Job.workspace_id == workspace_id)
        return self._session.execute(stmt).scalar_one_or_none()

    def sync_remote_job(self, channel: str, item: RemoteJobSyncItem) -> tuple[Job, JobPublication, bool]:
        """将渠道侧岗位映射为本地岗位与发布记录。"""
        publication = self.find_publication_by_external_job_id(channel, item.external_job_id)
        created = False
        now = datetime.now(UTC).replace(tzinfo=None)

        if publication is None:
            job = Job(
                workspace_id=get_workspace_id(self._session),
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
        workspace_id = get_workspace_id(self._session)
        if workspace_id:
            stmt = stmt.join(Job, Job.id == JobPublication.job_id).where(Job.workspace_id == workspace_id)
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
        workspace_id = get_workspace_id(self._session)
        if workspace_id:
            stmt = stmt.join(Job, Job.id == JobPublication.job_id).where(Job.workspace_id == workspace_id)
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

    def delete(self, job_id: str) -> None:
        """Delete one job."""
        job = self.get(job_id)
        self._session.delete(job)
        self._session.commit()

    def delete_many(self, job_ids: list[str]) -> int:
        """Delete many jobs and return deleted count."""
        unique_ids = list(dict.fromkeys([item for item in job_ids if item]))
        if not unique_ids:
            return 0
        stmt = delete(Job).where(Job.id.in_(unique_ids))
        workspace_id = get_workspace_id(self._session)
        if workspace_id:
            stmt = stmt.where(Job.workspace_id == workspace_id)
        result = self._session.execute(stmt)
        self._session.commit()
        return int(result.rowcount or 0)

    def _filter_jobs(
        self,
        jobs: list[Job],
        *,
        platform: str | None,
        name: str | None,
        job_type: str | None,
        salary: str | None,
    ) -> list[Job]:
        platform_query = (platform or "").strip().lower()
        name_query = (name or "").strip().lower()
        type_query = (job_type or "").strip().lower()
        salary_query = (salary or "").strip().lower().replace(" ", "")

        result = jobs
        if platform_query:
            result = [
                job
                for job in result
                if any((pub.channel or "").strip().lower() == platform_query for pub in job.publications)
            ]
        if name_query:
            result = [job for job in result if name_query in (job.title or "").lower()]
        if type_query:
            result = [job for job in result if self._infer_job_type(job) == type_query]
        if salary_query:
            result = [
                job
                for job in result
                if salary_query in ((job.salary_range or "").lower().replace(" ", ""))
            ]
        return result

    @staticmethod
    def _infer_job_type(job: Job) -> str:
        text = " ".join(
            [
                str(job.title or ""),
                str(job.department or ""),
                str(job.requirements or ""),
            ]
        ).lower()
        internship_keywords = ("实习", "intern", "应届", "校招", "校园")
        if any(keyword in text for keyword in internship_keywords):
            return "intern"
        return "social"
