"""语音 Provider 工厂。"""

from __future__ import annotations

from ...core.config import Settings
from ...core.exceptions import InvalidConnectorConfigError
from .base import ASRProvider, TTSProvider
from .mock_providers import MockASRProvider, MockTTSProvider
from .openai_providers import OpenAIASRProvider, OpenAITTSProvider
from .tencent_providers import TencentASRProvider, TencentTTSProvider
from .aliyun_providers import AliyunASRProvider, AliyunNlsASRProvider


def create_asr_provider(settings: Settings) -> ASRProvider:
    provider = (settings.asr_provider or "mock").strip().lower()
    if provider == "mock":
        return MockASRProvider()
    if provider == "openai":
        return OpenAIASRProvider(
            api_key=settings.asr_api_key or settings.llm_api_key or "",
            base_url=settings.asr_base_url or settings.llm_base_url,
            timeout_ms=settings.asr_stream_timeout_ms,
        )
    if provider == "tencent":
        return TencentASRProvider(
            secret_id=settings.tencent_secret_id,
            secret_key=settings.tencent_secret_key,
            region=settings.tencent_region,
            timeout_ms=settings.asr_stream_timeout_ms,
            engine_type=settings.asr_tencent_engine_type,
            voice_format=settings.asr_tencent_voice_format,
            endpoint=settings.asr_base_url or "https://asr.tencentcloudapi.com",
            app_id=settings.asr_tencent_app_id,
            ws_base_url=settings.asr_tencent_ws_base_url,
            streaming_enabled=settings.asr_tencent_streaming_enabled,
            ws_allow_http_fallback=settings.asr_tencent_ws_allow_http_fallback,
            ws_expire_seconds=settings.asr_tencent_ws_expire_seconds,
            ws_session_ttl_seconds=settings.asr_tencent_ws_session_ttl_seconds,
            ws_partial_wait_ms=settings.asr_tencent_ws_partial_wait_ms,
            ws_final_wait_ms=settings.asr_tencent_ws_final_wait_ms,
            ws_open_timeout_ms=settings.asr_tencent_ws_open_timeout_ms,
            ws_single_connection_enabled=settings.asr_tencent_ws_single_connection_enabled,
            prewarm_enabled=settings.asr_tencent_prewarm_enabled,
            keepalive_interval_seconds=settings.asr_tencent_keepalive_interval_seconds,
            keepalive_pcm_ms=settings.asr_tencent_keepalive_pcm_ms,
            force_streaming=settings.asr_force_streaming,
            hotword_file=settings.asr_hotword_file,
        )
    if provider == "aliyun":
        return AliyunASRProvider(
            api_key=settings.asr_aliyun_api_key or settings.asr_api_key or "",
            model=settings.asr_aliyun_model,
            streaming_enabled=settings.asr_aliyun_streaming_enabled,
        )
    if provider == "aliyun_nls":
        return AliyunNlsASRProvider(
            appkey=settings.asr_aliyun_appkey or "",
            access_key_id=settings.aliyun_access_key_id or "",
            access_key_secret=settings.aliyun_access_key_secret or "",
            streaming_enabled=settings.asr_aliyun_streaming_enabled,
        )
    raise InvalidConnectorConfigError(f"Unsupported asr_provider='{settings.asr_provider}'")


def create_tts_provider(settings: Settings) -> TTSProvider:
    provider = (settings.tts_provider or "mock").strip().lower()
    if provider == "mock":
        return MockTTSProvider()
    if provider == "openai":
        return OpenAITTSProvider(
            api_key=settings.tts_api_key or settings.llm_api_key or "",
            base_url=settings.tts_base_url or settings.llm_base_url,
            timeout_ms=settings.tts_stream_timeout_ms,
        )
    if provider == "tencent":
        return TencentTTSProvider(
            secret_id=settings.tencent_secret_id,
            secret_key=settings.tencent_secret_key,
            region=settings.tencent_region,
            timeout_ms=settings.tts_stream_timeout_ms,
            app_id=settings.tts_tencent_app_id or settings.asr_tencent_app_id,
            voice_type=settings.tts_tencent_voice_type,
            sample_rate=settings.tts_tencent_sample_rate,
            codec=settings.tts_tencent_codec,
            endpoint=settings.tts_base_url or "https://tts.tencentcloudapi.com",
            ws_base_url=settings.tts_tencent_ws_base_url,
            ws_streaming_enabled=settings.tts_tencent_ws_streaming_enabled,
            ws_allow_http_fallback=settings.tts_tencent_ws_allow_http_fallback,
            ws_expire_seconds=settings.tts_tencent_ws_expire_seconds,
            ws_open_timeout_ms=settings.tts_tencent_ws_open_timeout_ms,
            ws_recv_timeout_ms=settings.tts_tencent_ws_recv_timeout_ms,
            first_chunk_size=settings.tts_first_chunk_size,
            warmup_enabled=settings.tts_warmup_enabled,
        )
    raise InvalidConnectorConfigError(f"Unsupported tts_provider='{settings.tts_provider}'")
