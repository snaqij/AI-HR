"""Credential management service."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from ..connectors.base import ConnectorCredentials
from ..core.security import decrypt_data, encrypt_data
from ..repositories.credentials import ChannelCredentialRepository
from .system_notifications import get_system_notification_service
from ..core.config import get_settings


logger = logging.getLogger(__name__)


class CredentialService:
    """Service for managing and resolving channel credentials."""

    def __init__(self, session: Session):
        self._session = session
        self._repository = ChannelCredentialRepository(session)
        self._notification_service = get_system_notification_service(session)

    def resolve_boss_credentials(self) -> ConnectorCredentials:
        """Resolve BOSS credentials, prioritizing DB storage with .env fallback."""
        settings = get_settings()
        credential = self._repository.get_active_by_channel("boss")
        
        # Start with default settings from ENV
        base_creds = {
            "account": settings.boss_account,
            "mode": settings.boss_mode,
            "secret": settings.boss_secret,
            "cookie_header": settings.boss_cookie_header,
            "base_url": settings.boss_base_url,
            "publish_path": settings.boss_publish_path,
            "status_path": settings.boss_status_path,
            "applicants_path": settings.boss_applicants_path,
            "greet_path": settings.boss_greet_path,
            "fetch_messages_path": settings.boss_fetch_messages_path,
            "send_message_path": settings.boss_send_message_path,
            "resume_detail_path": settings.boss_resume_detail_path,
            "list_jobs_path": settings.boss_list_jobs_path,
            "interview_schedule_path": settings.boss_interview_schedule_path,
            "interview_status_path": settings.boss_interview_status_path,
            "timeout_seconds": float(settings.boss_timeout_seconds),
        }

        if not credential:
            return ConnectorCredentials(**base_creds)
            
        try:
            config_str = decrypt_data(credential.encrypted_config)
            config = json.loads(config_str)
            
            # DB values override ENV values
            db_overrides = {
                "account": credential.account_name,
                "mode": config.get("mode"),
                "secret": config.get("secret"),
                "cookie_header": config.get("cookie_header"),
                "base_url": config.get("base_url"),
                "publish_path": config.get("publish_path"),
                "status_path": config.get("status_path"),
                "applicants_path": config.get("applicants_path"),
                "greet_path": config.get("greet_path"),
                "fetch_messages_path": config.get("fetch_messages_path"),
                "send_message_path": config.get("send_message_path"),
                "resume_detail_path": config.get("resume_detail_path"),
                "list_jobs_path": config.get("list_jobs_path"),
                "interview_schedule_path": config.get("interview_schedule_path"),
                "interview_status_path": config.get("interview_status_path"),
            }
            
            # Apply non-None overrides
            for key, val in db_overrides.items():
                if val is not None:
                    base_creds[key] = val
                    
            return ConnectorCredentials(**base_creds)
        except Exception as e:
            logger.error(f"Failed to resolve BOSS credentials from DB, falling back to ENV only: {e}")
            return ConnectorCredentials(**base_creds)

    def update_boss_cookie(self, cookie_header: str, account_name: str = "Primary Account") -> bool:
        """Update the stored BOSS cookie."""
        # We store minimal config that only overrides the cookie_header
        # In a more advanced version, we'd store the full config
        config = {
            "cookie_header": cookie_header,
            "mode": "live"
        }
        encrypted = encrypt_data(json.dumps(config))
        self._repository.update_credential("boss", encrypted, account_name=account_name)
        self._session.commit()
        return True

    def handle_credential_failure(self, channel: str, error_message: str | None = None) -> None:
        """Handle a detected credential failure by marking it and notifying admin."""
        credential = self._repository.get_active_by_channel(channel)
        if not credential:
            return

        logger.warning(f"Credential failure detected for {channel}: {error_message}")
        self._repository.mark_expired(credential.id, error_message=error_message)
        self._session.commit()
        
        # Send notification
        self._notification_service.send_credential_expired_alert(
            channel=channel,
            account_name=credential.account_name,
            error_message=error_message
        )


def get_credential_service(session: Session) -> CredentialService:
    return CredentialService(session)
