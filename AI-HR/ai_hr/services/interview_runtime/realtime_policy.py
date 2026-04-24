"""Realtime pause and turn-taking policy for interview stages."""

from __future__ import annotations

from dataclasses import dataclass

from ai_hr.services.interview_runtime.flow_policy import normalize_stage_code


@dataclass(frozen=True, slots=True)
class StageRealtimePolicy:
    """Realtime voice policy for a single interview stage."""

    soft_pause_ms: int
    likely_done_ms: int
    hard_done_ms: int
    max_force_finalize_ms: int
    resume_grace_ms: int
    min_speaking_hold_ms: int
    commit_guard_ms: int
    allow_prefetch: bool = False


DEFAULT_REALTIME_POLICY = StageRealtimePolicy(
    soft_pause_ms=560,
    likely_done_ms=910,
    hard_done_ms=1400,
    max_force_finalize_ms=3150,
    resume_grace_ms=210,
    min_speaking_hold_ms=0,
    commit_guard_ms=450,
    allow_prefetch=False,
)


STAGE_REALTIME_POLICIES: dict[str, StageRealtimePolicy] = {
    "S1": StageRealtimePolicy(
        soft_pause_ms=350,
        likely_done_ms=630,
        hard_done_ms=980,
        max_force_finalize_ms=2240,
        resume_grace_ms=175,
        min_speaking_hold_ms=0,
        commit_guard_ms=350,
        allow_prefetch=False,
    ),
    "S2": StageRealtimePolicy(
        soft_pause_ms=1200,
        likely_done_ms=2000,
        hard_done_ms=3000,
        max_force_finalize_ms=3000,
        resume_grace_ms=400,
        min_speaking_hold_ms=6000,
        commit_guard_ms=700,
        allow_prefetch=False,
    ),

    "S3": StageRealtimePolicy(
        soft_pause_ms=800,
        likely_done_ms=2000,
        hard_done_ms=4500,
        max_force_finalize_ms=3000,
        resume_grace_ms=350,
        min_speaking_hold_ms=2000,
        commit_guard_ms=700,
        allow_prefetch=False,
    ),

    "S4": StageRealtimePolicy(
        soft_pause_ms=1000,
        likely_done_ms=3000,
        hard_done_ms=5000,
        max_force_finalize_ms=4000,
        resume_grace_ms=400,
        min_speaking_hold_ms=4000,
        commit_guard_ms=900,
        allow_prefetch=False,
    ),

    "S5": StageRealtimePolicy(
        soft_pause_ms=900,
        likely_done_ms=2800,
        hard_done_ms=4800,
        max_force_finalize_ms=4000,
        resume_grace_ms=400,
        min_speaking_hold_ms=3500,
        commit_guard_ms=800,
        allow_prefetch=False,
    ),

    "S6": StageRealtimePolicy(
        soft_pause_ms=840,
        likely_done_ms=1400,
        hard_done_ms=1960,
        max_force_finalize_ms=3360,
        resume_grace_ms=455,
        min_speaking_hold_ms=4800,
        commit_guard_ms=850,
        allow_prefetch=False,
    ),

    "S7": StageRealtimePolicy(
        soft_pause_ms=700,
        likely_done_ms=1260,
        hard_done_ms=1750,
        max_force_finalize_ms=3150,
        resume_grace_ms=350,
        min_speaking_hold_ms=3500,
        commit_guard_ms=700,
        allow_prefetch=False,
    ),

    "S8": StageRealtimePolicy(
        soft_pause_ms=420,
        likely_done_ms=700,
        hard_done_ms=1050,
        max_force_finalize_ms=2240,
        resume_grace_ms=175,
        min_speaking_hold_ms=0,
        commit_guard_ms=400,
        allow_prefetch=False,
    ),
}


def get_stage_realtime_policy(stage_code: str | None) -> StageRealtimePolicy:
    """Return realtime policy for the active stage."""

    return STAGE_REALTIME_POLICIES.get(
        normalize_stage_code(stage_code),
        DEFAULT_REALTIME_POLICY,
    )
