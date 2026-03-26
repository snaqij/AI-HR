"""AI 面试会话 API Schema。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AIInterviewSessionCreateRequest(BaseModel):
    """创建 AI 面试会话请求。"""

    candidate_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    channel: str = Field(default="self_hosted_rtc", min_length=1, max_length=64)
    language: str = Field(default="zh-CN", pattern="^(zh-CN|en-US)$")
    note: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class AIInterviewSessionResponse(BaseModel):
    """AI 面试会话响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    candidate_id: str
    job_id: str
    status: str
    channel: str
    language: str
    rtc_room_id: str
    join_token: str
    join_url: str
    started_at: datetime | None
    ended_at: datetime | None
    payload: dict[str, Any]
    note: str | None
    created_at: datetime
    updated_at: datetime


class AIInterviewSessionCreateResult(BaseModel):
    """创建 AI 面试会话结果。"""

    session: AIInterviewSessionResponse


class AIInterviewSessionStartRequest(BaseModel):
    """开始会话请求。"""

    operator: str = Field(default="system", min_length=1, max_length=64)


class AIInterviewSessionFinishRequest(BaseModel):
    """结束会话请求。"""

    result_status: str = Field(default="completed", pattern="^(completed|failed)$")
    operator: str = Field(default="system", min_length=1, max_length=64)
    note: str | None = None


class AIInterviewSessionHandoffRequest(BaseModel):
    """人工接管请求。"""

    reason: str = Field(min_length=1, max_length=128)
    trigger_flags: list[str] = Field(default_factory=list)
    operator: str = Field(default="system", min_length=1, max_length=64)
    note: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class AIInterviewSessionEventRequest(BaseModel):
    """实时事件上报请求。"""

    event_id: str = Field(min_length=1, max_length=128)
    seq: int = Field(default=1, ge=1)
    speaker: str = Field(default="candidate", min_length=1, max_length=32)
    transcript: str | None = None
    audio_base64: str | None = None
    audio_uri: str | None = None
    confidence: float | None = None
    latency_ms: int | None = None
    policy_flags: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)


class AIInterviewSessionEventResult(BaseModel):
    """实时事件上报结果。"""

    session_id: str
    event_id: str
    accepted: bool
    deduplicated: bool
    turn_id: str | None = None
    action: str | None = None
    decision_reason: str | None = None
    policy_flags: list[str] = Field(default_factory=list)
    interview_stage: str | None = None
    followup_question: str | None = None
    followup_audio_uris: list[str] = Field(default_factory=list)
    runtime_mode: str | None = None
    model_route: str | None = None
    degradation_mode: str | None = None
    latency_breakdown: dict[str, int] = Field(default_factory=dict)


class AIInterviewSessionHandoffResult(BaseModel):
    """人工接管结果。"""

    session: AIInterviewSessionResponse
    handoff_id: str


class AIInterviewQuestionGenerateRequest(BaseModel):
    """生成面试问题集请求。"""

    question_count: int = Field(default=8, ge=1, le=20)
    source: str = Field(default="resume+jd", min_length=1, max_length=64)
    force_regenerate: bool = True


class AIInterviewQuestionItem(BaseModel):
    """单条面试问题项。"""

    question: str
    dimension: str
    expected_signal: str
    followup_condition: str


class AIInterviewQuestionGenerateResult(BaseModel):
    """面试问题集生成结果。"""

    session_id: str
    version: int
    question_count: int
    source: str
    questions: list[AIInterviewQuestionItem] = Field(default_factory=list)


class AIInterviewQuestionPackPrebuildRequest(BaseModel):
    """预生成面试题包请求。"""

    candidate_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    language: str = Field(default="zh-CN", pattern="^(zh-CN|en-US)$")
    question_count: int = Field(default=10, ge=1, le=20)
    source: str = Field(default="resume+jd", min_length=1, max_length=64)


class AIInterviewQuestionPackPrebuildResult(BaseModel):
    """预生成面试题包结果。"""

    cache_key: str
    question_count: int
    expires_in_seconds: int
    source: str


class AIInterviewReportResponse(BaseModel):
    """AI 面试报告响应。"""

    session_id: str
    report_version: int
    summary: str
    dimension_scores: dict[str, float] = Field(default_factory=dict)
    risk_tags: list[str] = Field(default_factory=list)
    recommendation: str
    runtime_mode: str
    run_id: str


class AIInterviewReplayTurnItem(BaseModel):
    """会话回放中的单轮数据。"""

    turn_id: str
    turn_no: int
    speaker: str
    transcript: str | None = None
    audio_uri: str | None = None
    confidence: float | None = None
    latency_ms: int | None = None
    policy_flags: list[str] = Field(default_factory=list)
    occurred_at: datetime


class AIInterviewReplayResponse(BaseModel):
    """会话回放结果。"""

    session_id: str
    total_turns: int
    items: list[AIInterviewReplayTurnItem] = Field(default_factory=list)


class AIInterviewMetricsResponse(BaseModel):
    """AI 面试治理指标与告警结果。"""

    window_minutes: int
    total: int
    handoff_count: int
    blocked_count: int
    handoff_rate: float
    blocked_rate: float
    asr_p50_ms: float
    asr_p95_ms: float
    asr_p99_ms: float
    llm_p50_ms: float
    llm_p95_ms: float
    llm_p99_ms: float
    tts_p50_ms: float
    tts_p95_ms: float
    tts_p99_ms: float
    e2e_p50_ms: float
    e2e_p95_ms: float
    e2e_p99_ms: float
    latency_p95_ms: float
    llm_first_token_p95_ms: float = 0.0
    tts_first_packet_p95_ms: float = 0.0
    followup_repeat_rate: float = 0.0
    prefetch_hit_rate: float = 0.0
    question_completion_rate: float = 0.0
    video_policy_applied_count: int = 0
    video_policy_applied_rate: float = 0.0
    video_recording_enabled_count: int = 0
    video_recording_enabled_rate: float = 0.0
    alerting: bool
    alert_reasons: list[str] = Field(default_factory=list)


class AIInterviewRTCJoinRequest(BaseModel):
    """RTC 入会请求。"""

    candidate_id: str = Field(min_length=1)
    client_id: str = Field(default="web", min_length=1, max_length=64)


class AIInterviewRTCJoinResponse(BaseModel):
    """RTC 入会响应。"""

    session_id: str
    room_id: str
    join_token: str
    reconnectable: bool
    transport: str


class AIInterviewRTCReconnectRequest(BaseModel):
    """RTC 重连请求。"""

    client_id: str = Field(default="web", min_length=1, max_length=64)
    reason: str = Field(default="network_jitter", min_length=1, max_length=128)


class AIInterviewRTCReconnectResponse(BaseModel):
    """RTC 重连响应。"""

    session_id: str
    room_id: str
    reconnected: bool
    reconnect_count: int


class AIInterviewRTCAudioSubscribeRequest(BaseModel):
    """RTC 候选人音轨订阅请求。"""

    candidate_id: str = Field(min_length=1)
    client_id: str = Field(default="web", min_length=1, max_length=64)
    participant_identity: str | None = Field(default=None, min_length=1, max_length=128)
    subscriber_identity: str | None = Field(default=None, min_length=1, max_length=128)
    track_sids: list[str] = Field(default_factory=list)
    auto_subscribe: bool | None = None


class AIInterviewRTCAudioSubscribeResponse(BaseModel):
    """RTC 候选人音轨订阅响应。"""

    session_id: str
    room_id: str
    participant_identity: str
    subscriber_identity: str
    subscribed: bool
    mode: str
    track_sids: list[str] = Field(default_factory=list)
    feature_enabled: bool


class AIInterviewRTCVideoPolicyRequest(BaseModel):
    """RTC 视频轨策略请求。"""

    candidate_id: str = Field(min_length=1)
    client_id: str = Field(default="web", min_length=1, max_length=64)
    participant_identity: str | None = Field(default=None, min_length=1, max_length=128)
    subscriber_identity: str | None = Field(default=None, min_length=1, max_length=128)
    track_sids: list[str] = Field(default_factory=list)
    auto_subscribe: bool | None = None
    record_enabled: bool | None = None


class AIInterviewRTCVideoPolicyResponse(BaseModel):
    """RTC 视频轨策略响应。"""

    session_id: str
    room_id: str
    participant_identity: str
    subscriber_identity: str
    applied: bool
    subscribed: bool
    recording_enabled: bool
    mode: str
    track_sids: list[str] = Field(default_factory=list)
    feature_enabled: bool


class AIInterviewASRStreamRequest(BaseModel):
    """ASR 流式适配请求。"""

    seq: int = Field(ge=1)
    text_hint: str = Field(default="", max_length=2000)
    audio_base64: str | None = None
    audio_bytes: bytes | None = None
    confidence: float = Field(default=0.9, ge=0, le=1)
    latency_ms: int = Field(default=500, ge=1, le=10000)
    chunk_id: str | None = Field(default=None, min_length=1, max_length=128)
    chunk_index: int = Field(default=1, ge=1, le=10000)
    chunk_total: int = Field(default=1, ge=1, le=10000)
    is_final: bool = True
    input_format: str = Field(default="wav", min_length=1, max_length=32)
    target_latency_ms: int = Field(default=700, ge=100, le=5000)
    source: str = Field(default="api", min_length=1, max_length=64)
    participant_identity: str | None = Field(default=None, min_length=1, max_length=128)
    track_sid: str | None = Field(default=None, min_length=1, max_length=128)


class AIInterviewASRStreamResponse(BaseModel):
    """ASR 流式适配响应。"""

    session_id: str
    seq: int
    transcript: str
    provider: str | None = None
    asr_meta: dict[str, Any] = Field(default_factory=dict)
    confidence: float
    latency_ms: int
    p95_target_met: bool
    event_id: str | None = None
    turn_id: str | None = None
    deduplicated: bool = False
    chunk_index: int = 1
    chunk_total: int = 1
    is_final: bool = True
    is_partial: bool = False
    target_latency_ms: int = 700
    realtime_target_met: bool = True
    latency_breakdown: dict[str, int] = Field(default_factory=dict)


class AIInterviewTTSStreamRequest(BaseModel):
    """TTS 流式播报请求。"""

    text: str = Field(min_length=1, max_length=2000)
    voice: str = Field(default="default", min_length=1, max_length=64)
    chunk_size: int = Field(default=24, ge=8, le=120)
    publish_to_rtc: bool | None = None
    bot_identity: str | None = Field(default=None, min_length=1, max_length=128)
    track_name: str = Field(default="ai-bot-tts", min_length=1, max_length=128)
    target_latency_ms: int = Field(default=800, ge=100, le=5000)


class AIInterviewTTSStreamResponse(BaseModel):
    """TTS 流式播报响应。"""

    session_id: str
    voice: str
    chunks: list[str] = Field(default_factory=list)
    audio_uris: list[str] = Field(default_factory=list)
    published: bool = False
    bot_identity: str | None = None
    track_sid: str | None = None
    publish_mode: str | None = None
    target_latency_ms: int = 800
    realtime_target_met: bool = True
    p95_target_met: bool = True
    latency_breakdown: dict[str, int] = Field(default_factory=dict)


class AIInterviewRTCASRIngestRequest(BaseModel):
    """RTC room audio frame ingestion request."""

    room_id: str = Field(min_length=1, max_length=128)
    seq: int = Field(default=1, ge=1)
    frame_id: str | None = Field(default=None, min_length=1, max_length=128)
    text_hint: str = Field(default="", max_length=2000)
    audio_base64: str | None = None
    confidence: float = Field(default=0.9, ge=0, le=1)
    latency_ms: int = Field(default=320, ge=1, le=10000)
    chunk_index: int = Field(default=1, ge=1, le=10000)
    chunk_total: int = Field(default=1, ge=1, le=10000)
    is_final: bool = True
    input_format: str = Field(default="pcm", min_length=1, max_length=32)
    target_latency_ms: int = Field(default=700, ge=100, le=5000)
    participant_identity: str | None = Field(default=None, min_length=1, max_length=128)
    track_sid: str | None = Field(default=None, min_length=1, max_length=128)
    auto_followup: bool = True
    auto_tts_publish: bool = True
    tts_voice: str = Field(default="default", min_length=1, max_length=64)
    tts_chunk_size: int = Field(default=24, ge=8, le=120)
    tts_target_latency_ms: int = Field(default=1200, ge=100, le=5000)


class AIInterviewRTCASRIngestResponse(BaseModel):
    """RTC room audio frame ingestion response."""

    session_id: str
    room_id: str
    asr: AIInterviewASRStreamResponse
    event: AIInterviewSessionEventResult | None = None
    tts: AIInterviewTTSStreamResponse | None = None


class AIInterviewRTCWebhookResponse(BaseModel):
    """RTC webhook writeback response."""

    accepted: bool
    deduplicated: bool = False
    vendor: str = "livekit"
    event_type: str | None = None
    event_id: str | None = None
    room_id: str | None = None
    session_id: str | None = None
    reason: str | None = None
