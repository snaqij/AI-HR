"""外部 Provider 健康检查服务。"""

from __future__ import annotations

from urllib.parse import urlparse

from ...core.config import Settings
from .circuit_breaker import ProviderCircuitBreaker


class ProviderHealthService:
    """聚合 RTC/LLM/ASR/TTS 的健康状态。"""

    def __init__(self, *, settings: Settings, circuit_breaker: ProviderCircuitBreaker):
        self._settings = settings
        self._breaker = circuit_breaker

    def get_health(self) -> dict[str, dict]:
        """返回所有 provider 健康状态。"""
        return {
            "rtc": self._check_rtc(),
            "llm": self._check_llm(),
            "asr": self._check_asr(),
            "tts": self._check_tts(),
        }

    def _check_rtc(self) -> dict:
        provider = self._settings.rtc_provider
        if provider == "mock":
            return self._ok(provider, extra={"mode": "mock"})
        if provider == "livekit":
            reasons = []
            if not self._settings.livekit_base_url:
                reasons.append("livekit_base_url_missing")
            if not self._settings.livekit_api_key:
                reasons.append("livekit_api_key_missing")
            if not self._settings.livekit_api_secret:
                reasons.append("livekit_api_secret_missing")
            if reasons:
                return self._error(provider, reasons=reasons)
            return self._ok(provider, extra={"mode": "livekit", "endpoint": self._normalize_url(self._settings.livekit_base_url)})
        if provider == "agora":
            reasons = []
            if not self._settings.agora_app_id:
                reasons.append("agora_app_id_missing")
            if reasons:
                return self._error(provider, reasons=reasons)
            return self._ok(
                provider,
                extra={
                    "mode": "agora",
                    "app_id": self._settings.agora_app_id,
                    "room_prefix": self._settings.agora_room_prefix,
                },
            )
        return self._error(provider, reasons=["rtc_provider_unsupported"])

    def _check_llm(self) -> dict:
        provider = self._settings.llm_provider
        if provider == "mock":
            return self._ok(provider, extra={"mode": "mock"})
        if provider == "openai":
            if not self._settings.llm_api_key:
                return self._error(provider, reasons=["llm_api_key_missing"])
            return self._ok(provider, extra={"mode": "openai", "base_url": self._settings.llm_base_url or "default"})
        return self._error(provider, reasons=["llm_provider_unsupported"])

    def _check_asr(self) -> dict:
        provider = self._settings.asr_provider
        if provider == "mock":
            return self._ok(provider, extra={"mode": "mock"})
        if not self._settings.asr_api_key:
            return self._error(provider, reasons=["asr_api_key_missing"])
        return self._ok(provider, extra={"mode": provider, "base_url": self._settings.asr_base_url or "default"})

    def _check_tts(self) -> dict:
        provider = self._settings.tts_provider
        if provider == "mock":
            return self._ok(provider, extra={"mode": "mock"})
        if not self._settings.tts_api_key:
            return self._error(provider, reasons=["tts_api_key_missing"])
        return self._ok(provider, extra={"mode": provider, "base_url": self._settings.tts_base_url or "default"})

    def _ok(self, provider: str, *, extra: dict | None = None) -> dict:
        payload = {
            "provider": provider,
            "healthy": True,
            "reasons": [],
            "circuit": self._breaker.snapshot(provider),
        }
        if extra:
            payload.update(extra)
        return payload

    def _error(self, provider: str, *, reasons: list[str]) -> dict:
        payload = {
            "provider": provider,
            "healthy": False,
            "reasons": reasons,
            "circuit": self._breaker.snapshot(provider),
        }
        return payload

    @staticmethod
    def _normalize_url(raw: str | None) -> str | None:
        if not raw:
            return None
        parsed = urlparse(raw)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
        return raw
