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

        subject = f"【告警】AI-HR 系统凭据过期通知 - {channel.upper()}"
        body = (
            f"您好，管理员：\n\n"
            f"系统检测到以下渠道的凭据已失效或过期，自动化任务已暂停：\n\n"
            f"- 渠道：{channel}\n"
            f"- 账号别名：{account_name}\n"
            f"- 错误信息：{error_message or '未知原因'}\n\n"
            f"请尽快登录后台系统更新 Cookie，以恢复自动化招聘功能。\n\n"
            f"--- AI-HR 自动化招聘系统 ---"
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
