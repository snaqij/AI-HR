"""Shared domain constants for AI-HR."""

from .agent_state import AgentState
from .events import InterviewEventType
from .interview_action import InterviewAction
from .interview_stage import InterviewStage, InterviewStageGroup
from .model_route import ModelRoutePolicy, ModelRouteResult
from .payload_keys import PayloadKey
from .prompt_keys import PromptTaskKey
from .reporting import CandidateStageResult, InterviewOutcomeStatus, InterviewRecommendation, RuntimeMode
from .risk_flags import (
    BlockReason,
    GuardrailMaskToken,
    HandoffReason,
    RiskTag,
    SENSITIVE_FLAG_PREFIX,
    ValidationFlag,
    build_sensitive_flag,
)
from .runtime_commands import RuntimeCommand, RuntimeDataChannel
from .session_status import InterviewSessionStatus
from .speaker_role import SpeakerRole

__all__ = [
    "AgentState",
    "BlockReason",
    "GuardrailMaskToken",
    "HandoffReason",
    "InterviewAction",
    "InterviewEventType",
    "InterviewSessionStatus",
    "InterviewStage",
    "InterviewStageGroup",
    "ModelRoutePolicy",
    "ModelRouteResult",
    "PayloadKey",
    "PromptTaskKey",
    "CandidateStageResult",
    "InterviewOutcomeStatus",
    "InterviewRecommendation",
    "RuntimeMode",
    "RiskTag",
    "RuntimeCommand",
    "RuntimeDataChannel",
    "SENSITIVE_FLAG_PREFIX",
    "SpeakerRole",
    "ValidationFlag",
    "build_sensitive_flag",
]
