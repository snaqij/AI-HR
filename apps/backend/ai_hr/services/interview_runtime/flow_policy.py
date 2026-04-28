"""Interview flow policy definitions.

This module owns stage semantics and transition-related defaults.
The runtime state engine should consume these policies instead of
hard-coding interview behavior.

Role Configuration Integration:
- Supports session-level role configuration storage
- Allows stage policy overrides based on role config
- Maintains backward compatibility with existing code
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

# Session-level role configuration storage
# Format: {session_id: role_config_dict}
_SESSION_ROLE_CONFIGS: Dict[str, Dict[str, Any]] = {}


@dataclass(frozen=True, slots=True)
class StagePolicy:
    """Declarative policy for a single interview stage."""

    code: str
    name: str
    label: str
    description: str
    goal: str
    max_followups: int
    fallback_allowed: bool
    requires_question_pack: bool
    allow_llm_transition_signal: bool
    completion_mode: str = "question_driven"
    hard_max_turns: int = 0
    allow_deep_dive: bool = False
    topic_round_limit: int = 0
    must_exit_on_followup_limit: bool = True
    next_stage: str | None = None


STAGE_SEQUENCE: tuple[str, ...] = ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8")

STAGE_ALIASES: dict[str, str] = {
    "opening": "S1",
    "self_intro": "S2",
    "stack_verification": "S3",
    "project_deep_dive": "S4",
    "experience_validation": "S5",
    "capability_probe": "S6",
    "company_qa": "S7",
    "closing": "S8",
}

STAGE_POLICIES: dict[str, StagePolicy] = {
    "S1": StagePolicy(
        code="S1",
        name="opening",
        label="开场确认",
        description="确认连通状态后快速进入正式面试，不做长寒暄。",
        goal="确认语音和沟通状态正常，并迅速进入正式面试。",
        max_followups=0,
        fallback_allowed=False,
        requires_question_pack=False,
        allow_llm_transition_signal=False,
        completion_mode="signal_driven",
        hard_max_turns=1,
        allow_deep_dive=False,
        topic_round_limit=0,
        must_exit_on_followup_limit=True,
        next_stage="S2",
    ),
    "S2": StagePolicy(
        code="S2",
        name="self_intro",
        label="自我介绍",
        description="收集候选人最近经历、核心项目、角色定位和当前方向。",
        goal="让候选人完成简洁、聚焦的自我介绍，拿到最近经历与核心项目线索。",
        max_followups=2,
        fallback_allowed=False,
        requires_question_pack=True,
        allow_llm_transition_signal=True,
        completion_mode="hybrid",
        hard_max_turns=4,
        allow_deep_dive=False,
        topic_round_limit=2,
        must_exit_on_followup_limit=True,
        next_stage="S3",
    ),
    "S3": StagePolicy(
        code="S3",
        name="stack_verification",
        label="技术栈核验",
        description="围绕简历与项目核验技术栈的真实使用情况。",
        goal="基于项目验证候选人是否真正使用过关键技术栈，而不是只会名词。",
        max_followups=2,
        fallback_allowed=True,
        requires_question_pack=False,
        allow_llm_transition_signal=True,
        completion_mode="hybrid",
        hard_max_turns=6,
        allow_deep_dive=False,
        topic_round_limit=2,
        must_exit_on_followup_limit=True,
        next_stage="S4",
    ),
    "S4": StagePolicy(
        code="S4",
        name="project_deep_dive",
        label="项目深挖",
        description="深挖项目背景、职责、方案、难点、取舍和结果。",
        goal="拿到项目真实性、个人贡献、技术判断和结果指标的核心证据。",
        max_followups=2,
        fallback_allowed=True,
        requires_question_pack=True,
        allow_llm_transition_signal=True,
        completion_mode="question_driven",
        hard_max_turns=10,
        allow_deep_dive=True,
        topic_round_limit=3,
        must_exit_on_followup_limit=True,
        next_stage="S5",
    ),
    "S5": StagePolicy(
        code="S5",
        name="experience_validation",
        label="实习与岗位匹配",
        description="验证实习经历的参与深度，并补充岗位匹配证据。",
        goal="确认候选人在相关经历里是真正做过，还是只参与过，同时补足岗位匹配信息。",
        max_followups=2,
        fallback_allowed=True,
        requires_question_pack=True,
        allow_llm_transition_signal=True,
        completion_mode="question_driven",
        hard_max_turns=8,
        allow_deep_dive=True,
        topic_round_limit=3,
        must_exit_on_followup_limit=True,
        next_stage="S6",
    ),
    "S6": StagePolicy(
        code="S6",
        name="capability_probe",
        label="综合能力补充",
        description="补齐工程化、排障、表达与业务理解等剩余证据。",
        goal="补齐尚未确认的技术底子、排查思路、工程意识和表达能力证据。",
        max_followups=2,
        fallback_allowed=True,
        requires_question_pack=True,
        allow_llm_transition_signal=True,
        completion_mode="question_driven",
        hard_max_turns=4,
        allow_deep_dive=True,
        topic_round_limit=3,
        must_exit_on_followup_limit=True,
        next_stage="S7",
    ),
    "S7": StagePolicy(
        code="S7",
        name="company_qa",
        label="公司介绍与反问",
        description="自然介绍团队和岗位，并给候选人反问空间。",
        goal="用真实面试官口吻介绍公司与岗位，并自然回答候选人的问题。",
        max_followups=0,
        fallback_allowed=False,
        requires_question_pack=False,
        allow_llm_transition_signal=False,
        completion_mode="signal_driven",
        hard_max_turns=1,
        allow_deep_dive=False,
        topic_round_limit=0,
        must_exit_on_followup_limit=True,
        next_stage="S8",
    ),
    "S8": StagePolicy(
        code="S8",
        name="closing",
        label="收尾",
        description="简洁收尾，不做冗长结束语。",
        goal="简短结束面试并说明后续流程。",
        max_followups=0,
        fallback_allowed=False,
        requires_question_pack=False,
        allow_llm_transition_signal=False,
        completion_mode="signal_driven",
        hard_max_turns=1,
        allow_deep_dive=False,
        topic_round_limit=0,
        must_exit_on_followup_limit=True,
        next_stage=None,
    ),
}

EARLY_STAGE_CODES = frozenset({"S1", "S2"})
LATE_STAGE_CODES = frozenset({"S7", "S8"})
QUESTION_DRIVEN_STAGE_CODES = frozenset({"S3", "S4", "S5", "S6"})
DEFAULT_STAGE_CODE = "S1"


def normalize_stage_code(stage_code: str | None) -> str:
    """Return a supported stage code."""

    candidate = str(stage_code or "").strip()
    if candidate in STAGE_POLICIES:
        return candidate
    if candidate in STAGE_ALIASES:
        return STAGE_ALIASES[candidate]
    return DEFAULT_STAGE_CODE


def get_stage_policy(stage_code: str | None, session_id: str | None = None) -> StagePolicy:
    """
    Fetch stage policy with graceful fallback and optional role config override.
    
    Args:
        stage_code: Stage code (e.g., "S1", "S2")
        session_id: Optional session ID for role-specific overrides
    
    Returns:
        StagePolicy with role config overrides applied if available
    """
    base_policy = STAGE_POLICIES[normalize_stage_code(stage_code)]
    
    # If no session_id provided, return base policy
    if not session_id:
        return base_policy
    
    # Try to get role config for this session
    role_config = get_role_config_for_session(session_id)
    if not role_config:
        return base_policy
    
    # Apply role config overrides
    return _apply_role_config_overrides(base_policy, role_config)


def get_stage_definition(stage_code: str | None) -> dict[str, Any]:
    """Compatibility helper for callers that expect dict metadata."""

    return asdict(get_stage_policy(stage_code))


def get_next_stage(stage_code: str | None) -> str | None:
    """Return the configured next stage."""

    return get_stage_policy(stage_code).next_stage


def get_stage_hard_turn_limit(stage_code: str | None) -> int:
    """Return the hard cap of turns allowed within the stage."""

    return max(0, int(get_stage_policy(stage_code).hard_max_turns))


def get_stage_topic_round_limit(stage_code: str | None) -> int:
    """Return the max number of follow-up rounds for a single topic."""

    return max(0, int(get_stage_policy(stage_code).topic_round_limit))


def is_stage_deep_dive_allowed(stage_code: str | None) -> bool:
    """Whether the stage is allowed to drill into implementation details."""

    return bool(get_stage_policy(stage_code).allow_deep_dive)


def resolve_followup_limit(
    *,
    stage_code: str | None,
    question: dict[str, Any] | None = None,
    default: int | None = None,
    session_id: str | None = None,
) -> int:
    """
    Resolve max follow-up count for the active topic.
    
    Priority order:
    1. Question-specific limit (highest priority)
    2. Explicit default parameter
    3. Role config override (from session)
    4. Stage policy limit (lowest priority)
    
    Args:
        stage_code: Stage code
        question: Question dictionary with optional max_followups
        default: Explicit default value
        session_id: Optional session ID for role config overrides
    """
    # 1. Check question-specific limit
    question_limit = None
    if isinstance(question, dict):
        raw_limit = question.get("max_followups")
        if raw_limit is not None:
            try:
                question_limit = max(0, int(raw_limit))
            except (TypeError, ValueError):
                question_limit = None
    
    if question_limit is not None:
        return question_limit
    
    # 2. Check explicit default
    if default is not None:
        return max(0, int(default))
    
    # 3. Check role config override
    if session_id:
        role_config = get_role_config_for_session(session_id)
        if role_config:
            followup_strategy = role_config.get("followup_strategy", {})
            role_limit = followup_strategy.get("max_per_question")
            if role_limit is not None:
                try:
                    return max(0, int(role_limit))
                except (TypeError, ValueError):
                    pass
    
    # 4. Fall back to stage policy limit
    policy_limit = get_stage_policy(stage_code, session_id).max_followups
    return policy_limit


def derive_stage_goal(
    *,
    stage_code: str | None,
    question: dict[str, Any] | None = None,
) -> str:
    """Return the active stage goal, preferring question-specific signal."""

    policy = get_stage_policy(stage_code)
    if isinstance(question, dict):
        raw_signal = question.get("expected_signal") or question.get("success_signals")
        if isinstance(raw_signal, list):
            raw_signal = "、".join(str(item).strip() for item in raw_signal if str(item).strip())
        if raw_signal:
            return f"{policy.goal} 当前重点：{raw_signal}"
    return policy.goal


def derive_missing_evidence(
    *,
    question: dict[str, Any] | None = None,
    fallback: str = "",
) -> list[str]:
    """Generate a normalized missing-evidence list."""

    if not isinstance(question, dict):
        return [fallback] if fallback else []

    raw_value = question.get("expected_signal") or question.get("success_signals") or fallback
    if isinstance(raw_value, str):
        parts = [item.strip() for item in raw_value.replace("，", ",").replace("、", ",").split(",")]
        return [item for item in parts if item]
    if isinstance(raw_value, list):
        return [str(item).strip() for item in raw_value if str(item).strip()]
    return [fallback] if fallback else []


def build_stage_state_patch(
    *,
    stage_code: str | None,
    question: dict[str, Any] | None = None,
    previous_state: dict[str, Any] | None = None,
    transition_reason: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """
    Build consistent stage-related state metadata.
    
    Args:
        stage_code: Stage code
        question: Current question dictionary
        previous_state: Previous state dictionary
        transition_reason: Reason for stage transition
        session_id: Optional session ID for role config overrides
    """
    policy = get_stage_policy(stage_code, session_id)
    prior = previous_state or {}
    difficulty_level = str(prior.get("difficulty_level") or "normal")
    if difficulty_level not in {"normal", "fallback", "deep"}:
        difficulty_level = "normal"

    return {
        "interview_stage": policy.code,
        "interview_stage_name": policy.name,
        "interview_stage_label": policy.label,
        "interview_stage_description": policy.description,
        "stage_goal": derive_stage_goal(stage_code=policy.code, question=question),
        "difficulty_level": difficulty_level,
        "missing_evidence": derive_missing_evidence(question=question),
        "transition_reason": str(transition_reason or prior.get("transition_reason") or ""),
        "stage_max_followups": resolve_followup_limit(
            stage_code=policy.code,
            question=question,
            session_id=session_id
        ),
        "active_question_type": str((question or {}).get("question_type") or prior.get("active_question_type") or ""),
        "active_topic_name": str((question or {}).get("topic_name") or prior.get("active_topic_name") or ""),
    }


# ============================================================================
# Role Configuration Session Management
# ============================================================================


# ============================================================================
# Role Configuration Session Management
# ============================================================================


def _apply_role_config_overrides(base_policy: StagePolicy, role_config: Dict[str, Any]) -> StagePolicy:
    """
    Apply role configuration overrides to a base stage policy.
    
    Currently supports overriding:
    - max_followups: from role_config.followup_strategy.max_per_question
    - hard_max_turns / topic_round_limit / allow_deep_dive / completion_mode /
      requires_question_pack / goal: from role_config.stage_policy_overrides[stage_code]
    
    Args:
        base_policy: Base stage policy
        role_config: Role configuration dictionary
    
    Returns:
        New StagePolicy with overrides applied
    """
    # Extract override values from role config
    followup_strategy = role_config.get("followup_strategy", {})
    max_followups_override = followup_strategy.get("max_per_question")
    stage_policy_overrides = role_config.get("stage_policy_overrides", {})
    stage_override = stage_policy_overrides.get(base_policy.code, {}) if isinstance(stage_policy_overrides, dict) else {}

    # If no overrides, return base policy
    if max_followups_override is None and (not isinstance(stage_override, dict) or not stage_override):
        return base_policy

    # Create new policy with overrides
    # We use asdict to convert to dict, apply changes, then create new StagePolicy
    policy_dict = asdict(base_policy)

    if max_followups_override is not None:
        try:
            policy_dict["max_followups"] = max(0, int(max_followups_override))
        except (TypeError, ValueError):
            pass  # Keep original value if conversion fails

    if isinstance(stage_override, dict):
        int_fields = ("hard_max_turns", "topic_round_limit", "max_followups")
        bool_fields = ("allow_deep_dive", "requires_question_pack", "fallback_allowed", "allow_llm_transition_signal")
        str_fields = ("completion_mode", "goal", "description", "label", "next_stage")

        for field in int_fields:
            raw = stage_override.get(field)
            if raw is None:
                continue
            try:
                policy_dict[field] = max(0, int(raw))
            except (TypeError, ValueError):
                pass

        for field in bool_fields:
            raw = stage_override.get(field)
            if raw is not None:
                policy_dict[field] = bool(raw)

        for field in str_fields:
            raw = stage_override.get(field)
            if raw is not None:
                policy_dict[field] = str(raw)

    return StagePolicy(**policy_dict)


def set_role_config_for_session(session_id: str, role_config: Dict[str, Any]) -> None:
    """
    Store role configuration for a specific session.
    
    This allows stage policies to be customized based on the candidate's role.
    
    Args:
        session_id: Unique session identifier
        role_config: Role configuration dictionary from RoleConfigLoader
    
    Example:
        >>> role_config = role_profiler.identify_role(job_title="Backend Engineer")
        >>> set_role_config_for_session("session_123", role_config)
    """
    if not session_id:
        return
    
    _SESSION_ROLE_CONFIGS[session_id] = role_config or {}


def get_role_config_for_session(session_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve role configuration for a specific session.
    
    Args:
        session_id: Unique session identifier
    
    Returns:
        Role configuration dictionary, or None if not found
    
    Example:
        >>> role_config = get_role_config_for_session("session_123")
        >>> if role_config:
        ...     max_followups = role_config.get("followup_strategy", {}).get("max_per_question", 3)
    """
    if not session_id:
        return None
    
    return _SESSION_ROLE_CONFIGS.get(session_id)


def clear_role_config_for_session(session_id: str) -> None:
    """
    Clear role configuration for a specific session.
    
    Should be called when a session ends to prevent memory leaks.
    
    Args:
        session_id: Unique session identifier
    """
    if session_id in _SESSION_ROLE_CONFIGS:
        del _SESSION_ROLE_CONFIGS[session_id]
