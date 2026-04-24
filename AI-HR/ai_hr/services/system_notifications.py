"""System notification service for administrative alerts."""

from __future__ import annotations
import logging
import smtplib
from email.message import EmailMessage
from typing import Any
from sqlalchemy.orm import Session
from ..core.config import get_settings


logger = logging.getLogger(__name__)


class SystemNotificationService:
    """Handles system-level notifications like credential expiration alerts."""

    def __init__(self, session: Session):
        self._session = session
        self._settings = get_settings()

    def send_credential_expired_alert(self, channel: str, account_name: str, error_message: str | None = None) -> bool:
        """Sends an email alert to the admin when a channel credential expires."""
        recipient = self._settings.email_from_address
        if not recipient:
             logger.warning("No admin email (email_from_address) configured for alerts")
             return False

        subject = f"[ALERT] AI-HR Credential Expired - {channel.upper()}"
        body = (
            f"Hello, Admin:\n\n"
            f"The system has detected that the credentials for the following channel have expired or become invalid. Automated tasks have been paused:\n\n"
            f"- Channel: {channel}\n"
            f"- Account alias: {account_name}\n"
            f"- Error: {error_message or 'unknown reason'}\n\n"
            f"Please log in to the admin console and update the credentials to resume automated recruitment.\n\n"
            f"--- AI-HR Automated Recruitment System ---"
        )
        
        try:
            return self._send_email(recipient, subject, body)
        except Exception as e:
            logger.error(f"Failed to send system alert email: {e}")
            return False

    def _send_email(self, to_email: str, subject: str, body: str) -> bool:
        if not self._settings.email_smtp_host:
            logger.error("SMTP host not configured")
            return False

        message = EmailMessage()
        from_name = self._settings.email_from_name.strip()
        message["From"] = f"{from_name} <{self._settings.email_from_address or ''}>"
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(body)

        try:
            if self._settings.email_smtp_use_ssl:
                smtp_class = smtplib.SMTP_SSL
            else:
                smtp_class = smtplib.SMTP
            
            with smtp_class(self._settings.email_smtp_host, self._settings.email_smtp_port, timeout=15) as smtp:
                if self._settings.email_smtp_use_tls and not self._settings.email_smtp_use_ssl:
                    smtp.starttls()
                if self._settings.email_smtp_username:
                    smtp.login(
                        self._settings.email_smtp_username,
                        self._settings.email_smtp_password or "",
                    )
                smtp.send_message(message)
            return True
        except Exception as e:
            logger.exception(f"SMTP delivery failed: {e}")
            return False


def get_system_notification_service(session: Session) -> SystemNotificationService:
    return SystemNotificationService(session)
