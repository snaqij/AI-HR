"""Shared runtime orchestration for realtime interview turns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_hr.services.interview_runtime.flow_policy import (
    get_next_stage,
    get_stage_hard_turn_limit,
    get_stage_topic_round_limit,
    normalize_stage_code,
)
from ai_hr.services.interview_runtime.question_flow import InterviewQuestionFlowEngine
from ai_hr.services.interview_runtime.stage_progress import StageProgressEngine, StageProgressSnapshot


@dataclass(slots=True)
class RuntimeTurnDecision:
    """Structured flow decision for a single candidate turn."""

    updated_state: dict[str, Any]
    evaluation: dict[str, Any]
    stage: str
    current_question: dict[str, Any] | None
    next_stage: str
    next_action: str
    must_transition: bool
    flow_reason: str
    output_mode: str = "llm_followup"
    target_question: dict[str, Any] | None = None
    followup_budget_remaining: int = 0
    transition_brief: str = ""
    stage_progress_snapshot: StageProgressSnapshot | None = None


class InterviewRuntimeEngine:
    """Coordinate question flow and stage progress for one turn."""

    def __init__(
        self,
        *,
        question_flow_engine: InterviewQuestionFlowEngine | None = None,
        stage_progress_engine: StageProgressEngine | None = None,
    ) -> None:
        self.question_flow_engine = question_flow_engine or InterviewQuestionFlowEngine()
        self.stage_progress_engine = stage_progress_engine or StageProgressEngine()

    def init_runtime_state(self, *, question_pack: dict[str, Any]) -> dict[str, Any]:
        """Return a normalized initial runtime state."""

        return self.question_flow_engine.init_state(question_pack=question_pack)

    def _condense_focus_text(self, transcript: str) -> str:
        normalized = " ".join(str(transcript or "").strip().split())
        if not normalized:
            return ""
        for separator in ("。", "！", "？", ".", "!", "?", "，", ",", "；", ";"):
            if separator in normalized:
                normalized = normalized.split(separator, 1)[0].strip()
                break
        return normalized[:80]

    @staticmethod
    def _resolve_output_mode(
        *,
        updated_state: dict[str, Any],
        must_transition: bool,
        next_stage: str,
        current_stage: str,
        target_question: dict[str, Any] | None,
    ) -> str:
        if target_question and (must_transition or next_stage != current_stage):
            return "scripted_question"
        current_question_asked = bool(updated_state.get("current_question_asked"))
        current_question_status = str(updated_state.get("current_question_status") or "").strip()
        if current_question_asked and current_question_status in {"scripted_asked", "followup_active"}:
            return "llm_followup"
        if target_question:
            return "scripted_question"
        return "llm_followup"

    def process_candidate_turn(
        self,
        *,
        state: dict[str, Any],
        question_pack: dict[str, Any],
        transcript: str,
        confidence: float | None,
        force_complete: bool = False,
        candidate_requested_move_on: bool = False,
        topic_round_limit_reached: bool = False,
    ) -> RuntimeTurnDecision:
        """Process a single candidate answer and return the next flow action."""

        working_state = dict(state)
        stage = normalize_stage_code(working_state.get("interview_stage"))
        current_question = self.question_flow_engine.current_question(
            state=working_state,
            question_pack=question_pack,
        )
        question_dimension = str((current_question or {}).get("dimension") or "").strip().lower()
        focus_slot = str((current_question or {}).get("focus_slot") or "").strip().lower()
        topic_name = str((current_question or {}).get("topic_name") or question_dimension or "").strip()
        condensed_focus = self._condense_focus_text(transcript)
        if topic_name:
            working_state["active_topic_name"] = topic_name
        if focus_slot == "experience" and condensed_focus:
            working_state["focus_experience"] = condensed_focus
        elif focus_slot == "module" and condensed_focus:
            working_state["focus_module"] = condensed_focus

        evaluation = self.question_flow_engine.evaluate_answer(
            transcript=transcript,
            confidence=confidence,
            stage=stage,
        )

        stage_progress_snapshot: StageProgressSnapshot | None = None
        if stage == "S2":
            working_state, stage_progress_snapshot = self.stage_progress_engine.update(
                state=working_state,
                stage=stage,
                transcript=transcript,
            )

        hard_turn_limit = get_stage_hard_turn_limit(stage)
        next_stage_turn_count = max(0, int(working_state.get("stage_turn_count", 0))) + 1
        stage_turn_limit_reached = hard_turn_limit > 0 and next_stage_turn_count >= hard_turn_limit

        topic_round_limit = get_stage_topic_round_limit(stage)
        if not topic_round_limit_reached:
            topic_round_limit_reached = (
                topic_round_limit > 0 and max(0, int(working_state.get("active_topic_rounds", 0))) >= topic_round_limit
            )

        updated_state = self.question_flow_engine.apply_turn_result(
            state=working_state,
            evaluation=evaluation,
            question_pack=question_pack,
            current_q_max_followups=(current_question or {}).get("max_followups"),
            force_complete=force_complete,
            stage_progress_completed=bool(stage_progress_snapshot and stage_progress_snapshot.completed),
            candidate_requested_move_on=candidate_requested_move_on,
            stage_turn_limit_reached=stage_turn_limit_reached,
            topic_round_limit_reached=topic_round_limit_reached,
        )

        next_stage = normalize_stage_code(updated_state.get("interview_stage"))
        transition_reason = str(updated_state.get("transition_reason") or "")
        question_completion_reason = str(updated_state.get("question_completion_reason") or "")
        target_question = self.question_flow_engine.current_question(
            state=updated_state,
            question_pack=question_pack,
        )
        if not target_question and current_question and not question_completion_reason and next_stage == stage:
            target_question = current_question

        next_action = "followup"
        must_transition = False
        if candidate_requested_move_on:
            next_action = "next_question"
            must_transition = True
        elif next_stage != stage:
            next_action = "transition"
            must_transition = True
        elif question_completion_reason:
            next_action = "next_question"
            must_transition = True
        elif stage_progress_snapshot and stage_progress_snapshot.min_bar_passed and get_next_stage(stage):
            next_action = "transition"
            must_transition = True

        flow_reason = transition_reason or question_completion_reason or str(evaluation.get("reason") or "")
        output_mode = self._resolve_output_mode(
            updated_state=updated_state,
            must_transition=must_transition,
            next_stage=next_stage,
            current_stage=stage,
            target_question=target_question,
        )
        if output_mode == "scripted_question" and isinstance(target_question, dict):
            updated_state["current_question_id"] = str(
                target_question.get("question_id")
                or target_question.get("id")
                or updated_state.get("current_question_id")
                or ""
            ).strip()
            updated_state["current_question_status"] = "pending"
            updated_state["current_question_asked"] = False
            updated_state["current_output_mode"] = "scripted_question"
        else:
            updated_state["current_output_mode"] = "llm_followup"

        followup_limit = self.question_flow_engine.get_followup_limit(
            stage_code=next_stage or stage,
            question=target_question if output_mode == "llm_followup" else current_question,
        )
        followup_budget_remaining = max(
            0,
            int(followup_limit) - max(0, int(updated_state.get("followup_count_current", 0))),
        )
        transition_brief = flow_reason or next_action
        if stage_progress_snapshot and stage_progress_snapshot.min_bar_passed:
            updated_state["profile_collected"] = True

        return RuntimeTurnDecision(
            updated_state=updated_state,
            evaluation=evaluation,
            stage=stage,
            current_question=current_question,
            next_stage=next_stage,
            next_action=next_action,
            must_transition=must_transition,
            flow_reason=flow_reason,
            output_mode=output_mode,
            target_question=target_question,
            followup_budget_remaining=followup_budget_remaining,
            transition_brief=transition_brief,
            stage_progress_snapshot=stage_progress_snapshot,
        )
