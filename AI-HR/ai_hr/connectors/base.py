"""Connector abstractions for recruiting platforms."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class ConnectorCredentials:
    account: str
    secret: str
    mode: str = "mock"
    base_url: str | None = None
    publish_path: str | None = None
    status_path: str | None = None
    applicants_path: str | None = None
    greet_path: str | None = None
    fetch_messages_path: str | None = None
    send_message_path: str | None = None
    interview_schedule_path: str | None = None
    interview_status_path: str | None = None
    cookie_header: str | None = None
    credential_file: str | None = None
    timeout_seconds: float = 20.0


@dataclass(slots=True)
class PublishJobResult:
    channel: str
    external_job_id: str
    status: str
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SyncJobStatusResult:
    channel: str
    external_job_id: str
    status: str
    raw_payload: dict[str, Any] = field(default_factory=dict)


class RecruitingConnector(Protocol):
    channel: str

    def validate_credentials(self) -> None:
        """Validate connector configuration before any sync or command."""

    def publish_job(self, job_payload: dict[str, Any]) -> PublishJobResult:
        """Publish a job post to the external platform."""

    def sync_job_status(self, external_job_id: str) -> SyncJobStatusResult:
        """Fetch the latest publishing status from the external platform."""

    def list_applicants(self, job_external_id: str, cursor: str | None = None) -> dict[str, Any]:
        """Fetch job applicants with optional incremental cursor."""

    def send_greeting(
        self,
        candidate_external_id: str,
        template_id: str,
        variables: dict[str, Any],
    ) -> dict[str, Any]:
        """Send an outreach greeting to a candidate."""

    def fetch_messages(self, conversation_external_id: str, cursor: str | None = None) -> dict[str, Any]:
        """Fetch conversation messages."""

    def send_message(self, conversation_external_id: str, message: str) -> dict[str, Any]:
        """Send a direct message to a candidate."""

    def schedule_interview(self, candidate_external_id: str, slot: dict[str, Any]) -> dict[str, Any]:
        """Schedule an interview or trigger a scheduling flow."""

    def sync_interview_status(self, external_interview_id: str) -> dict[str, Any]:
        """Fetch interview status from external platform."""
