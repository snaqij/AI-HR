"""Application configuration definitions."""

from __future__ import annotations
import os
from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[4]
SYSTEM_ENV_FILENAME = "infra/env/.env.system"
SECRETS_ENV_FILENAME = "infra/env/.env.secrets"
ENV_FILE_MAP = {
    "dev": "infra/env/.env.dev",
    "development": "infra/env/.env.dev",
    "prod": "infra/env/.env.prod",
    "production": "infra/env/.env.prod",
}


class Settings(BaseSettings):
    """Application settings loaded from env vars and env files."""

    app_name: str = "AI-HR API"
    app_version: str = "0.1.0"
    api_prefix: str = "/api/v1"
    environment: str = "dev"
    debug: bool = False
    auto_create_tables: bool = False
    host: str = "127.0.0.1"
    port: int = 8000
    cors_allow_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    cors_allow_credentials: bool = False
    auth_enabled: bool = True
    auth_token_signing_key: str = "change-this-dev-signing-key"
    auth_access_token_ttl_seconds: int = 900
    auth_refresh_token_ttl_seconds: int = 60 * 60 * 24 * 30
    auth_password_pbkdf2_iterations: int = 310000
    auth_email_verification_code_ttl_seconds: int = 600
    auth_email_verification_resend_cooldown_seconds: int = 60
    auth_refresh_cookie_name: str = "aihr_refresh_token"
    auth_refresh_cookie_secure: bool = False
    auth_refresh_cookie_samesite: str = "lax"
    database_url: str = Field(default="mysql+pymysql://root:password@127.0.0.1:3306/ai_hr")
    ai_interview_auth_required: bool = False
    ai_interview_api_keys: str | None = None
    boss_mode: str = "live"
    boss_account: str = "demo-account"
    boss_secret: str = "demo-secret"
    boss_base_url: str = "https://www.zhipin.com"
    boss_publish_path: str = "/wapi/zpjob/job/publish.json"
    boss_status_path: str = "/wapi/zpjob/job/status.json"
    boss_list_jobs_path: str = "/wapi/zpjob/job/list.json"
    boss_applicants_path: str = "/wapi/zpjob/job/applicants.json"
    boss_greet_path: str = "/wapi/zpchat/greet/send.json"
    boss_fetch_messages_path: str = "/wapi/zpchat/conversation/messages.json"
    boss_send_message_path: str = "/wapi/zpchat/conversation/send.json"
    boss_resume_detail_path: str | None = None
    boss_interview_schedule_path: str = "/wapi/zpinterview/interview/schedule.json"
    boss_interview_status_path: str = "/wapi/zpinterview/interview/status.json"
    boss_cookie_header: str | None = None
    boss_credential_file: str | None = None
    boss_timeout_seconds: float = 20.0
    job_sync_scheduler_enabled: bool = False
    job_sync_scheduler_poll_seconds: int = 30
    job_sync_scheduler_batch_size: int = 10
    job_global_sync_enabled: bool = True
    job_global_sync_interval_minutes: int = 1440
    job_global_sync_max_pages: int = 5
    resume_access_retry_interval_minutes: int = 10
    resume_access_retry_batch_size: int = 20
    object_storage_enabled: bool = False
    object_storage_provider: str = "minio"
    object_storage_endpoint: str | None = None
    object_storage_access_key: str | None = None
    object_storage_secret_key: str | None = None
    object_storage_bucket: str = "ai-hr-resumes"
    object_storage_region: str | None = None
    object_storage_secure: bool = False
    object_storage_auto_create_bucket: bool = True
    object_storage_resume_prefix: str = "resume-attachments"
    object_storage_public_base_url: str | None = None
    object_storage_required: bool = False
    llm_provider: str = "mock"
    llm_model: str = "gpt-4.1-mini"
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_streaming_enabled: bool = True
    llm_timeout_seconds: int = 30
    llm_max_retries: int = 2
    ai_resume_llm_enabled: bool = False
    ai_scoring_llm_enabled: bool = False
    ai_candidate_evaluation_llm_enabled: bool = True
    ai_candidate_evaluation_recommend_score: float = 72.0
    ai_candidate_evaluation_strong_recommend_score: float = 85.0
    ai_candidate_evaluation_batch_size: int = 20
    ai_auto_invitation_enabled: bool = False
    ai_auto_invitation_batch_size: int = 20
    ai_auto_invitation_template_code: str = "interview_invitation_default"
    interview_invitation_base_url: str = "http://localhost:5173/interview/invitation/{token}"
    email_smtp_host: str | None = None
    email_smtp_port: int = 587
    email_smtp_username: str | None = None
    email_smtp_password: str | None = None
    email_smtp_use_tls: bool = True
    email_smtp_use_ssl: bool = False
    email_from_name: str = "深澜智远招聘"
    email_from_address: str | None = None
    credential_expired_alert_cooldown_minutes: int = 360
    ai_reply_llm_enabled: bool = False
    ai_interview_llm_enabled: bool = False
    ai_reply_auto_min_confidence: float = 0.65
    ai_reply_sensitive_block_enabled: bool = True
    ai_reply_alert_window_minutes: int = 60
    ai_reply_handoff_alert_threshold: float = 0.30
    ai_reply_blocked_alert_threshold: float = 0.10
    ai_reply_alert_min_samples: int = 10
    provider_circuit_breaker_fail_threshold: int = 3
    provider_circuit_breaker_cooldown_seconds: int = 30
    rtc_provider: str = "mock"
    rtc_default_transport: str = "webrtc"
    rtc_token_ttl_seconds: int = 3600
    agora_app_id: str | None = None
    agora_app_certificate: str | None = None
    agora_room_prefix: str = "ai-intv-"
    agora_token_ttl_seconds: int = 14400
    agora_ten_bot_user_id_prefix: str = "aihr-bot-"
    ai_interview_rtc_audio_subscribe_enabled: bool = False
    ai_interview_rtc_audio_subscribe_auto: bool = True
    ai_interview_rtc_audio_track_ids: str | None = None
    ai_interview_rtc_audio_subscriber_identity: str = "ai-bot"
    ai_interview_rtc_tts_publish_enabled: bool = False
    ai_interview_rtc_tts_bot_identity: str = "ai-bot"
    ai_interview_rtc_video_policy_enabled: bool = False
    ai_interview_rtc_video_subscribe_auto: bool = True
    ai_interview_rtc_video_record_enabled: bool = False
    ai_interview_rtc_video_track_ids: str | None = None
    ai_interview_rtc_video_subscriber_identity: str = "ai-bot"
    ai_interview_rtc_duplex_ws_enabled: bool = True
    ai_interview_rtc_asr_ingest_ws_enabled: bool = True
    ai_interview_ten_enabled: bool = False
    ai_interview_ten_auto_launch: bool = False
    ai_interview_ten_agent_dir: str | None = None
    ai_interview_ten_tman_cmd: str = "tman"
    ai_interview_ten_session_dir: str | None = None
    ai_interview_ten_property_template: str | None = None
    ai_interview_duplex_seen_frame_window: int = 2048
    ai_interview_duplex_partial_trigger_enabled: bool = True
    ai_interview_duplex_partial_min_chars: int = 8
    ai_interview_duplex_partial_dedup_ttl_ms: int = 1500
    asr_provider: str = "mock"
    asr_force_streaming: bool = False
    asr_api_key: str | None = None
    asr_base_url: str | None = None
    asr_stream_timeout_ms: int = 5000
    asr_hotword_file: str | None = "technical_hot_words.txt"
    asr_aliyun_api_key: str | None = None
    asr_aliyun_model: str = "paraformer-realtime-v1"
    asr_aliyun_streaming_enabled: bool = True
    asr_aliyun_appkey: str | None = None
    aliyun_access_key_id: str | None = None
    aliyun_access_key_secret: str | None = None
    asr_tencent_engine_type: str = "16k_zh"
    asr_tencent_voice_format: int = 4
    asr_tencent_app_id: str | None = None
    asr_tencent_ws_base_url: str = "wss://asr.cloud.tencent.com/asr/v2"
    asr_tencent_streaming_enabled: bool = True
    asr_tencent_ws_allow_http_fallback: bool = True
    asr_tencent_ws_expire_seconds: int = 90
    asr_tencent_ws_session_ttl_seconds: int = 45
    asr_tencent_ws_partial_wait_ms: int = 35
    asr_tencent_ws_final_wait_ms: int = 800
    asr_tencent_ws_open_timeout_ms: int = 800
    asr_tencent_ws_single_connection_enabled: bool = True
    asr_tencent_prewarm_enabled: bool = True
    asr_tencent_keepalive_interval_seconds: int = 8
    asr_tencent_keepalive_pcm_ms: int = 40
    tts_provider: str = "mock"
    tts_force_streaming: bool = True
    tts_api_key: str | None = None
    tts_base_url: str | None = None
    tts_stream_timeout_ms: int = 5000
    tts_tencent_voice_type: int = 101001
    tts_tencent_sample_rate: int = 16000
    tts_tencent_codec: str = "pcm"
    tts_tencent_app_id: str | None = None
    tts_tencent_ws_base_url: str = "wss://tts.cloud.tencent.com/stream_wsv2"
    tts_tencent_ws_streaming_enabled: bool = True
    tts_tencent_ws_allow_http_fallback: bool = False
    tts_tencent_ws_expire_seconds: int = 90
    tts_tencent_ws_open_timeout_ms: int = 1200
    tts_tencent_ws_recv_timeout_ms: int = 1200
    tts_first_chunk_size: int = 12
    tts_warmup_enabled: bool = True
    redis_url: str | None = None
    ai_interview_redis_enabled: bool = False
    ai_interview_redis_prefix: str = "aihr"
    ai_interview_question_pack_ttl_seconds: int = 172800
    ai_interview_state_ttl_seconds: int = 172800
    ai_interview_followup_cache_ttl_seconds: int = 180
    ai_interview_prebuild_pack_ttl_seconds: int = 604800
    ai_interview_redis_event_bus_enabled: bool = False
    ai_interview_persistence_worker_enabled: bool = True
    tencent_secret_id: str | None = None
    tencent_secret_key: str | None = None
    tencent_region: str = "ap-guangzhou"
    ai_interview_transcript_retention_days: int = 180
    ai_interview_audio_retention_days: int = 30
    ai_interview_event_retention_days: int = 365
    ai_interview_cleanup_batch_size: int = 500
    ai_interview_question_count_default: int = 14
    ai_interview_question_count_min: int = 1
    ai_interview_question_count_max: int = 20
    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_prefix="AI_HR_",
    )


def _resolve_legacy_env_file() -> Path:
    """Resolve legacy single env file path from explicit path or environment alias."""
    explicit_env_file = os.getenv("AI_HR_ENV_FILE")
    if explicit_env_file:
        return Path(explicit_env_file).expanduser().resolve()

    environment = os.getenv("AI_HR_ENV", "dev").lower()
    filename = ENV_FILE_MAP.get(environment, "infra/env/.env.dev")
    return PROJECT_ROOT / filename


def _resolve_project_env_file(*, env_var: str, default_filename: str) -> Path:
    raw_value = os.getenv(env_var, "").strip()
    if raw_value:
        candidate = Path(raw_value).expanduser()
        return candidate if candidate.is_absolute() else (PROJECT_ROOT / candidate).resolve()
    return PROJECT_ROOT / default_filename


def _resolve_env_files() -> tuple[Path, ...]:
    """Resolve ordered env files; prefer split system/secret files when present."""
    explicit_env_file = os.getenv("AI_HR_ENV_FILE", "").strip()
    if explicit_env_file:
        return (Path(explicit_env_file).expanduser().resolve(),)

    system_env = _resolve_project_env_file(env_var="AI_HR_SYSTEM_ENV_FILE", default_filename=SYSTEM_ENV_FILENAME)
    secret_env = _resolve_project_env_file(env_var="AI_HR_SECRET_ENV_FILE", default_filename=SECRETS_ENV_FILENAME)
    split_files = tuple(path for path in (system_env, secret_env) if path.exists())
    if split_files:
        return split_files

    return (_resolve_legacy_env_file(),)


@lru_cache
def get_settings() -> Settings:
    """Return process-level cached Settings instance."""
    env_files = tuple(path for path in _resolve_env_files() if path.exists())
    if env_files:
        last_error: UnicodeDecodeError | None = None
        for encoding in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
            try:
                return Settings(_env_file=env_files, _env_file_encoding=encoding)
            except UnicodeDecodeError as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
    return Settings()
