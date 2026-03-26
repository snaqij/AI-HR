"""Job service orchestrates job-related use cases."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..connectors.base import ConnectorCredentials
from ..connectors.registry import registry
from ..core.config import get_settings
from ..core.exceptions import ConnectorOperationError
from ..repositories.candidates import CandidateRepository
from ..repositories.jobs import JobRepository
from ..schemas.candidates import CandidateImportItem
from ..schemas.jobs import JobCandidateSyncRequest, JobCreateRequest, JobPublishRequest


class JobService:
    def __init__(self, repository: JobRepository, candidate_repository: CandidateRepository):
        self._repository = repository
        self._candidate_repository = candidate_repository
        self._settings = get_settings()

    def create_job(self, payload: JobCreateRequest):
        return self._repository.create(payload)

    def get_job(self, job_id: str):
        return self._repository.get(job_id)

    def publish_job(self, job_id: str, payload: JobPublishRequest):
        job = self._repository.get(job_id)
        for channel in payload.channels:
            publication_request = {
                "title": job.title,
                "department": job.department,
                "city": job.city,
                "salary_range": job.salary_range,
                "requirements": job.requirements,
            }
            try:
                connector = self._build_connector(channel)
                result = connector.publish_job(publication_request)
                self._repository.add_publication(
                    job,
                    channel=channel,
                    status=result.status,
                    request_payload=publication_request,
                    response_payload=result.raw_payload,
                    external_job_id=result.external_job_id,
                )
            except ConnectorOperationError as exc:
                self._repository.add_publication(
                    job,
                    channel=channel,
                    status="failed",
                    request_payload=publication_request,
                    response_payload={},
                    error_message=str(exc),
                )
        return self._repository.get(job_id)

    def get_publish_status(self, job_id: str):
        job = self._repository.get(job_id)
        for publication in list(job.publications):
            if not publication.external_job_id:
                continue
            try:
                connector = self._build_connector(publication.channel)
                sync_result = connector.sync_job_status(publication.external_job_id)
                self._repository.update_publication_sync_result(
                    publication.id,
                    status=sync_result.status,
                    response_payload=sync_result.raw_payload,
                )
            except ConnectorOperationError as exc:
                self._repository.update_publication_sync_result(
                    publication.id,
                    status="failed",
                    response_payload={},
                    error_message=str(exc),
                )

        job = self._repository.get(job_id)
        return {
            "job_id": job.id,
            "publications": list(job.publications),
        }

    def sync_candidates(self, job_id: str, payload: JobCandidateSyncRequest):
        job = self._repository.get(job_id)
        allowed_channels = set(payload.channels or [])
        sync_targets = []
        for publication in list(job.publications):
            if not publication.external_job_id:
                continue
            if allowed_channels and publication.channel not in allowed_channels:
                continue
            sync_targets.append(publication)

        channel_results: list[dict] = []
        total_pulled = 0
        total_created = 0
        total_updated = 0

        for publication in sync_targets:
            connector = self._build_connector(publication.channel)
            cursor = publication.applicant_sync_cursor
            pulled_count = 0
            created_count = 0
            updated_count = 0
            has_more = False

            for _ in range(payload.max_pages):
                result = connector.list_applicants(publication.external_job_id, cursor=cursor)
                items = result.get("items", [])
                candidate_items = [
                    CandidateImportItem(
                        name=item.get("name", "Unknown"),
                        source_channel=publication.channel,
                        external_candidate_id=item["external_candidate_id"],
                        phone_hash=item.get("phone_hash"),
                        email_hash=item.get("email_hash"),
                        resume_url=item.get("resume_url"),
                        resume_text=item.get("resume_text"),
                        raw_profile=item.get("raw_profile", {}),
                    )
                    for item in items
                    if item.get("external_candidate_id")
                ]

                if candidate_items:
                    _, page_created, page_updated = self._candidate_repository.upsert_many(candidate_items)
                    created_count += page_created
                    updated_count += page_updated
                pulled_count += len(candidate_items)

                cursor = result.get("next_cursor")
                has_more = bool(result.get("has_more", False))
                if not has_more or cursor is None:
                    break

            self._repository.update_publication_cursor(publication.id, cursor)
            channel_results.append(
                {
                    "channel": publication.channel,
                    "external_job_id": publication.external_job_id,
                    "pulled_count": pulled_count,
                    "created_count": created_count,
                    "updated_count": updated_count,
                    "next_cursor": cursor,
                    "has_more": has_more,
                }
            )
            total_pulled += pulled_count
            total_created += created_count
            total_updated += updated_count

        return {
            "job_id": job.id,
            "total_pulled": total_pulled,
            "total_created": total_created,
            "total_updated": total_updated,
            "channels": channel_results,
        }

    def _build_connector(self, channel: str):
        if channel == "boss":
            credentials = ConnectorCredentials(
                account=self._settings.boss_account,
                secret=self._settings.boss_secret,
                mode=self._settings.boss_mode,
                base_url=self._settings.boss_base_url,
                publish_path=self._settings.boss_publish_path,
                status_path=self._settings.boss_status_path,
                applicants_path=self._settings.boss_applicants_path,
                greet_path=self._settings.boss_greet_path,
                fetch_messages_path=self._settings.boss_fetch_messages_path,
                send_message_path=self._settings.boss_send_message_path,
                interview_schedule_path=self._settings.boss_interview_schedule_path,
                interview_status_path=self._settings.boss_interview_status_path,
                cookie_header=self._settings.boss_cookie_header,
                credential_file=self._settings.boss_credential_file,
                timeout_seconds=self._settings.boss_timeout_seconds,
            )
            return registry.create(channel, credentials)
        raise ConnectorOperationError(f"Connector settings for channel '{channel}' are not configured")


def get_job_service(session: Session) -> JobService:
    return JobService(JobRepository(session), CandidateRepository(session))
