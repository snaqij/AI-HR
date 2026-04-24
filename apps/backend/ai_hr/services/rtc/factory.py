"""RTC 网关工厂。"""

from __future__ import annotations

from ...core.config import Settings
from ...core.exceptions import InvalidConnectorConfigError
from .agora_gateway import AgoraConfig, AgoraRTCGateway
from .base import RTCGateway
from .mock_gateway import MockRTCGateway


def create_rtc_gateway(settings: Settings) -> RTCGateway:
    """根据配置创建 RTC 网关。"""
    provider = (settings.rtc_provider or "mock").strip().lower()
    if provider == "mock":
        return MockRTCGateway()
    if provider == "agora":
        if not settings.agora_app_id:
            raise InvalidConnectorConfigError("Agora provider requires app_id")
        return AgoraRTCGateway(
            AgoraConfig(
                app_id=settings.agora_app_id,
                app_certificate=settings.agora_app_certificate,
                room_prefix=settings.agora_room_prefix,
                token_ttl_seconds=settings.agora_token_ttl_seconds,
                ten_bot_user_id_prefix=settings.agora_ten_bot_user_id_prefix,
            )
        )
    raise InvalidConnectorConfigError(f"Unsupported rtc_provider='{settings.rtc_provider}'")
