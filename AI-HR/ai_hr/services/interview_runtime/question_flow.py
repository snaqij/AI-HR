"""State engine for structured interview runtime."""

from __future__ import annotations

from typing import Any

from ai_hr.services.interview_runtime.flow_policy import (
    EARLY_STAGE_CODES,
    LATE_STAGE_CODES,
    QUESTION_DRIVEN_STAGE_CODES,
    build_stage_state_patch,
    get_next_stage,
    get_stage_definition,
    normalize_stage_code,
    resolve_followup_limit,
)


class InterviewQuestionFlowEngine:
    """Manage question pointer and stage metadata without owning policy."""

    def init_state(self, *, question_pack: dict[str, Any]) -> dict[str, Any]:
        """Create a normalized initial interview state."""

        questions = question_pack.get("questions", []) if isinstance(question_pack, dict) else []
        question_count = len(questions) if isinstance(questions, list) else 0
        state = {
            "active_question_index": 0,
            "question_statuses": ["pending"] * question_count,
            "followup_count_current": 0,
            "completed_questions": 0,
            "interview_stage": "S1",
            "context_flags": {
                "greeted": False,
                "connectivity_confirmed": False,
                "intro_ready": False,
                "company_info_shared": False,
                "closing_started": False,
            },
            "interview_stage_name": "",
            "interview_stage_label": "",
            "interview_stage_description": "",
            "stage_goal": "",
            "missing_evidence": [],
            "stage_progress": {"S2": {}, "S3": {}},
            "difficulty_level": "normal",
            "transition_reason": "initialized",
            "stage_max_followups": 0,
        }
        return self.sync_stage_metadata(state=state, stage_code="S1", transition_reason="initialized")

    def current_question(self, *, state: dict[str, Any], question_pack: dict[str, Any]) -> dict[str, Any] | None:
        """Return the active question."""

        questions = question_pack.get("questions", []) if isinstance(question_pack, dict) else []
        if not isinstance(questions, list) or not questions:
            return None
        idx = int(state.get("active_question_index", 0))
        if idx < 0 or idx >= len(questions):
            return None
        question = questions[idx]
        if isinstance(question, dict):
            return {"index": idx, **question}
        return None

    def evaluate_answer(self, *, transcript: str, confidence: float | None, min_len: int = 15) -> dict[str, Any]:
        """Estimate whether the current answer needs follow-up."""

        normalized = " ".join((transcript or "").strip().split())
        need_followup = False
        reason = "sufficient"
        fallback_recommended = False

        if not normalized or len(normalized) < 4:
            need_followup = True
            reason = "too_short_or_noise"
        elif confidence is not None and confidence < 0.50:
            need_followup = True
            reason = "low_confidence"
            fallback_recommended = True
        elif len(normalized) < int(min_len):
            need_followup = True
            reason = "insufficient_detail"
        elif " " in normalized and len(set(normalized.split())) <= 2 and len(normalized) > 10:
            need_followup = True
            reason = "repetitive_content"
            fallback_recommended = True

        return {
            "need_followup": need_followup,
            "reason": reason,
            "normalized_len": len(normalized),
            "confidence": confidence,
            "fallback_recommended": fallback_recommended,
        }

    def get_stage_definition(self, stage_code: str) -> dict[str, Any]:
        """Return compatibility stage metadata."""

        return get_stage_definition(stage_code)

    def get_stage_name(self, stage_code: str) -> str:
        return str(self.get_stage_definition(stage_code).get("name", "unknown"))

    def get_stage_label(self, stage_code: str) -> str:
        return str(self.get_stage_definition(stage_code).get("label", stage_code))

    def get_followup_limit(
        self,
        *,
        stage_code: str,
        question: dict[str, Any] | None = None,
        default: int | None = None,
    ) -> int:
        """Return follow-up limit using policy and question override."""

        return resolve_followup_limit(stage_code=stage_code, question=question, default=default)

    def sync_stage_metadata(
        self,
        *,
        state: dict[str, Any],
        stage_code: str,
        question: dict[str, Any] | None = None,
        transition_reason: str | None = None,
    ) -> dict[str, Any]:
        """Synchronize stage metadata onto state."""

        merged = dict(state)
        merged.update(
            build_stage_state_patch(
                stage_code=stage_code,
                question=question,
                previous_state=merged,
                transition_reason=transition_reason,
            )
        )
        return merged

    def transition_stage(
        self,
        *,
        state: dict[str, Any],
        stage_code: str,
        question: dict[str, Any] | None = None,
        transition_reason: str | None = None,
        reset_followup: bool = True,
    ) -> dict[str, Any]:
        """Move state into a different stage in a consistent way."""

        merged = dict(state)
        if reset_followup:
            merged["followup_count_current"] = 0
        return self.sync_stage_metadata(
            state=merged,
            stage_code=stage_code,
            question=question,
            transition_reason=transition_reason,
        )

    def apply_turn_result(
        self,
        *,
        state: dict[str, Any],
        evaluation: dict[str, Any],
        current_q_max_followups: int | None = None,
        max_followup_per_question: int | None = None,
        force_complete: bool = False,
    ) -> dict[str, Any]:
        """Update question progress after one turn."""

        merged = dict(state)
        statuses = list(merged.get("question_statuses", []))
        current_stage = normalize_stage_code(merged.get("interview_stage", "S1"))

        if not statuses:
            return self.sync_stage_metadata(
                state=merged,
                stage_code=self.derive_stage(state=merged),
                transition_reason="no_question_pack",
            )

        idx = max(0, int(merged.get("active_question_index", 0)))
        if idx >= len(statuses):
            return self.sync_stage_metadata(
                state=merged,
                stage_code=self.derive_stage(state=merged),
                transition_reason="question_pack_exhausted",
            )

        if current_stage in EARLY_STAGE_CODES:
            return self.sync_stage_metadata(state=merged, stage_code=current_stage)

        followup_limit = self.get_followup_limit(
            stage_code=current_stage,
            question=None,
            default=current_q_max_followups if current_q_max_followups is not None else max_followup_per_question,
        )
        need_followup = bool(evaluation.get("need_followup"))
        followup_count = max(0, int(merged.get("followup_count_current", 0)))

        if force_complete or not need_followup or followup_count >= followup_limit:
            statuses[idx] = "completed" if (not need_followup or force_complete) else "completed_with_gap"
            merged["active_question_index"] = idx + 1
            merged["followup_count_current"] = 0
            merged["transition_reason"] = "question_completed" if (not need_followup or force_complete) else "followup_limit_reached"
        else:
            statuses[idx] = "asked"
            merged["followup_count_current"] = followup_count + 1
            merged["transition_reason"] = str(evaluation.get("reason") or "followup_needed")

        merged["question_statuses"] = statuses
        merged["completed_questions"] = sum(1 for item in statuses if str(item).startswith("completed"))

        if evaluation.get("fallback_recommended"):
            merged["difficulty_level"] = "fallback"
        elif force_complete:
            merged["difficulty_level"] = "normal"

        next_stage = self.derive_stage(state=merged)
        return self.sync_stage_metadata(
            state=merged,
            stage_code=next_stage,
            transition_reason=str(merged.get("transition_reason") or ""),
        )

    def derive_stage(self, *, state: dict[str, Any]) -> str:
        """Derive stage code from progress."""

        active_stage = normalize_stage_code(state.get("interview_stage"))
        if active_stage in LATE_STAGE_CODES or active_stage in EARLY_STAGE_CODES:
            return active_stage

        statuses = list(state.get("question_statuses", []))
        active_idx = int(state.get("active_question_index", 0))

        if statuses and active_idx >= len(statuses):
            return get_next_stage(active_stage) or "S7"

        if active_stage in QUESTION_DRIVEN_STAGE_CODES:
            return active_stage
        return "S1"
