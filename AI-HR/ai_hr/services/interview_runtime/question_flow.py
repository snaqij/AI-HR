"""State engine for structured interview runtime."""

from __future__ import annotations

from typing import Any

from ai_hr.services.interview_runtime.flow_policy import (
    LATE_STAGE_CODES,
    QUESTION_DRIVEN_STAGE_CODES,
    build_stage_state_patch,
    get_next_stage,
    get_stage_hard_turn_limit,
    get_stage_definition,
    normalize_stage_code,
    resolve_followup_limit,
)


class InterviewQuestionFlowEngine:
    """Manage question pointer and stage metadata without owning policy."""

    @staticmethod
    def _questions(question_pack: dict[str, Any]) -> list[dict[str, Any]]:
        raw_questions = question_pack.get("questions", []) if isinstance(question_pack, dict) else []
        return [item for item in raw_questions if isinstance(item, dict)]

    def _resolve_stage_question_index(
        self,
        *,
        state: dict[str, Any],
        question_pack: dict[str, Any],
        stage_code: str | None = None,
    ) -> int | None:
        questions = self._questions(question_pack)
        if not questions:
            return None

        statuses = list(state.get("question_statuses", []))
        active_stage = normalize_stage_code(stage_code or state.get("interview_stage"))
        preferred_start = max(0, int(state.get("active_question_index", 0)))

        def _matches(idx: int) -> bool:
            if idx < 0 or idx >= len(questions):
                return False
            question = questions[idx]
            if normalize_stage_code(question.get("stage")) != active_stage:
                return False
            status = str(statuses[idx] if idx < len(statuses) else "pending")
            return not status.startswith("completed")

        for idx in range(preferred_start, len(questions)):
            if _matches(idx):
                return idx
        for idx in range(0, preferred_start):
            if _matches(idx):
                return idx
        return None

    def _stage_has_pending_questions(
        self,
        *,
        state: dict[str, Any],
        question_pack: dict[str, Any],
        stage_code: str,
    ) -> bool:
        return self._resolve_stage_question_index(
            state=state,
            question_pack=question_pack,
            stage_code=stage_code,
        ) is not None

    def _resolve_next_pending_stage(
        self,
        *,
        state: dict[str, Any],
        question_pack: dict[str, Any],
        current_stage: str,
    ) -> str | None:
        next_stage = get_next_stage(current_stage)
        while next_stage:
            normalized = normalize_stage_code(next_stage)
            if normalized in LATE_STAGE_CODES:
                return normalized
            if self._stage_has_pending_questions(
                state=state,
                question_pack=question_pack,
                stage_code=normalized,
            ):
                return normalized
            next_stage = get_next_stage(normalized)
        return None

    @staticmethod
    def _next_state_version(state: dict[str, Any]) -> int:
        return max(1, int(state.get("state_version", 0))) + 1

    def _build_question_runtime_patch(
        self,
        *,
        state: dict[str, Any],
        question: dict[str, Any] | None,
        question_status: str | None = None,
        output_mode: str | None = None,
        question_asked: bool | None = None,
    ) -> dict[str, Any]:
        patch = {
            "current_question_id": str(state.get("current_question_id") or "").strip(),
            "current_question_status": str(state.get("current_question_status") or "").strip(),
            "current_question_asked": bool(state.get("current_question_asked", False)),
        }
        if isinstance(question, dict):
            patch["current_question_id"] = str(
                question.get("question_id")
                or question.get("id")
                or state.get("current_question_id")
                or ""
            ).strip()
            patch["current_question_status"] = str(
                question_status
                or state.get("current_question_status")
                or "pending"
            ).strip()
            patch["current_question_asked"] = bool(
                question_asked
                if question_asked is not None
                else state.get("current_question_asked", False)
            )
        if output_mode is not None:
            patch["current_output_mode"] = str(output_mode).strip()
        return patch

    def init_state(self, *, question_pack: dict[str, Any]) -> dict[str, Any]:
        """Create a normalized initial interview state."""

        questions = question_pack.get("questions", []) if isinstance(question_pack, dict) else []
        question_count = len(questions) if isinstance(questions, list) else 0
        state = {
            "active_question_index": 0,
            "question_statuses": ["pending"] * question_count,
            "question_stage_sequence": [
                normalize_stage_code(item.get("stage")) if isinstance(item, dict) else ""
                for item in questions
            ],
            "followup_count_current": 0,
            "completed_questions": 0,
            "stage_turn_count": 0,
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
            "question_completion_reason": "",
            "focus_experience": "",
            "focus_module": "",
            "active_question_type": "",
            "active_topic_name": "",
            "active_topic_rounds": 0,
            "candidate_requested_move_on": False,
            "profile_collected": False,
            "current_question_id": "",
            "current_question_status": "",
            "current_question_asked": False,
            "current_output_mode": "",
            "state_version": 1,
        }
        return self.sync_stage_metadata(state=state, stage_code="S1", transition_reason="initialized")

    def current_question(self, *, state: dict[str, Any], question_pack: dict[str, Any]) -> dict[str, Any] | None:
        """Return the active question."""

        questions = self._questions(question_pack)
        if not questions:
            return None
        idx = self._resolve_stage_question_index(state=state, question_pack=question_pack)
        if idx is None:
            return None
        question = questions[idx]
        return {"index": idx, **question}

    def evaluate_answer(
        self,
        *,
        transcript: str,
        confidence: float | None,
        min_len: int = 15,
        stage: str | None = None,
    ) -> dict[str, Any]:
        """Estimate whether the current answer needs follow-up."""

        normalized = " ".join((transcript or "").strip().split())
        need_followup = False
        reason = "sufficient"
        fallback_recommended = False

        # Adjust thresholds for technical stages
        active_min_len = min_len
        if stage in ("S3", "S4", "S5"):
            # Technical answers must be at least 12 characters to be considered "Initial Substance"
            active_min_len = max(min_len, 12)

        if not normalized or len(normalized) < 4:
            need_followup = True
            reason = "too_short_or_noise"
        elif confidence is not None and confidence < 0.40:
            need_followup = True
            reason = "low_confidence"
            fallback_recommended = True
        elif len(normalized) < active_min_len:
            # We still tag this for reason logging, but flow logic will ignore sufficiency for tech stages
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
        if isinstance(question, dict) and question.get("index") is not None:
            with_index = question.get("index")
            try:
                merged["active_question_index"] = max(0, int(with_index))
            except (TypeError, ValueError):
                pass
        merged.update(
            build_stage_state_patch(
                stage_code=stage_code,
                question=question,
                previous_state=merged,
                transition_reason=transition_reason,
            )
        )
        merged.update(self._build_question_runtime_patch(state=merged, question=question))
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
        merged["stage_turn_count"] = 0
        merged["active_topic_rounds"] = 0
        merged["state_version"] = self._next_state_version(merged)
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
        question_pack: dict[str, Any] | None = None,
        current_q_max_followups: int | None = None,
        max_followup_per_question: int | None = None,
        force_complete: bool = False,
        stage_progress_completed: bool = False,
        candidate_requested_move_on: bool = False,
        stage_turn_limit_reached: bool = False,
        topic_round_limit_reached: bool = False,
    ) -> dict[str, Any]:
        """Update question progress after one turn."""

        merged = dict(state)
        statuses = list(merged.get("question_statuses", []))
        current_stage = normalize_stage_code(merged.get("interview_stage", "S1"))
        merged["stage_turn_count"] = max(0, int(merged.get("stage_turn_count", 0))) + 1
        merged["candidate_requested_move_on"] = bool(candidate_requested_move_on)

        if not statuses:
            return self.sync_stage_metadata(
                state=merged,
                stage_code=self.derive_stage(state=merged, question_pack=question_pack),
                transition_reason="no_question_pack",
            )

        if question_pack:
            idx = self._resolve_stage_question_index(
                state=merged,
                question_pack=question_pack,
                stage_code=current_stage,
            )
        else:
            idx = max(0, int(merged.get("active_question_index", 0)))
            if idx >= len(statuses):
                idx = None
        if idx is None:
            return self.sync_stage_metadata(
                state=merged,
                stage_code=self.derive_stage(state=merged, question_pack=question_pack),
                transition_reason="stage_question_pack_exhausted",
            )
        merged["active_question_index"] = idx

        followup_limit = self.get_followup_limit(
            stage_code=current_stage,
            question=None,
            default=current_q_max_followups if current_q_max_followups is not None else max_followup_per_question,
        )
        need_followup = bool(evaluation.get("need_followup"))
        followup_count = max(0, int(merged.get("followup_count_current", 0)))
        hard_turn_limit = get_stage_hard_turn_limit(current_stage)
        stage_turn_limit_reached = bool(
            stage_turn_limit_reached or (hard_turn_limit > 0 and int(merged.get("stage_turn_count", 0)) >= hard_turn_limit)
        )
        current_question_id = str(merged.get("current_question_id") or f"q_{idx}").strip()

        completion_reason = ""
        should_complete = False
        completed_with_gap = False
        if force_complete or stage_progress_completed:
            should_complete = True
            completion_reason = "question_completed"
        elif candidate_requested_move_on:
            should_complete = True
            completed_with_gap = True
            completion_reason = "candidate_requested_move_on"
        elif not need_followup:
            # Technical stages require both technical signal and turn-based depth.
            # We never transition based purely on answer length for S3, S4, and S5.
            if current_stage not in ("S3", "S4", "S5"):
                should_complete = True
                completion_reason = "question_completed"
        elif topic_round_limit_reached:
            should_complete = True
            completed_with_gap = True
            completion_reason = "topic_exhausted"
        elif stage_turn_limit_reached:
            should_complete = True
            completed_with_gap = True
            completion_reason = "stage_turn_limit_reached"
        elif followup_count >= followup_limit:
            should_complete = True
            completed_with_gap = True
            completion_reason = "followup_limit_reached"




        if should_complete:
            statuses[idx] = "completed_with_gap" if completed_with_gap else "completed"
            merged["active_question_index"] = idx + 1
            merged["followup_count_current"] = 0
            merged["active_topic_rounds"] = 0
            merged["question_completion_reason"] = completion_reason
            merged["transition_reason"] = completion_reason
            merged["current_question_id"] = current_question_id
            merged["current_question_status"] = statuses[idx]
            merged["current_question_asked"] = True
            merged["current_output_mode"] = "scripted_question"
        else:
            statuses[idx] = "followup_active" if followup_count > 0 else "scripted_asked"
            merged["followup_count_current"] = followup_count + 1
            merged["active_topic_rounds"] = max(0, int(merged.get("active_topic_rounds", 0))) + 1
            merged["question_completion_reason"] = ""
            merged["transition_reason"] = str(evaluation.get("reason") or "followup_needed")
            merged["current_question_id"] = current_question_id
            merged["current_question_status"] = statuses[idx]
            merged["current_question_asked"] = True
            merged["current_output_mode"] = "llm_followup"

        merged["question_statuses"] = statuses
        merged["completed_questions"] = sum(1 for item in statuses if str(item).startswith("completed"))
        merged["state_version"] = self._next_state_version(merged)

        if evaluation.get("fallback_recommended"):
            merged["difficulty_level"] = "fallback"
        elif force_complete:
            merged["difficulty_level"] = "normal"

        next_stage = self.derive_stage(state=merged, question_pack=question_pack)
        return self.sync_stage_metadata(
            state=merged,
            stage_code=next_stage,
            transition_reason=str(merged.get("transition_reason") or ""),
        )

    def derive_stage(self, *, state: dict[str, Any], question_pack: dict[str, Any] | None = None) -> str:
        """Derive stage code from progress."""

        active_stage = normalize_stage_code(state.get("interview_stage"))
        completion_reason = str(state.get("question_completion_reason") or "").strip()
        if active_stage == "S1":
            return active_stage
        if active_stage == "S2":
            # 1. Check global turn limit for S2 (Hard Limit enforcement)
             # Note: merged["stage_turn_count"] is incremented at the start of apply_turn_result.
            hard_limit = get_stage_hard_turn_limit("S2") or 4
            stage_turns = int(state.get("stage_turn_count", 0))
            if stage_turns >= hard_limit or completion_reason in ("followup_limit_reached", "stage_turn_limit_reached"):
                return "S3"

            # 2. Check for scripted questions
            if question_pack and self._stage_has_pending_questions(
                state=state,
                question_pack=question_pack,
                stage_code="S2",
            ):
                return "S2"

            # 3. Handle Empty S2 Pack or completed scripted intro
            # If no S2 scripted questions exist, but we haven't reached limits,
            # transition to S3 as soon as any S2 turn is completed normally.
            if completion_reason and (not question_pack or not self._stage_has_pending_questions(state=state, question_pack=question_pack, stage_code="S2")):
                return "S3"
            
            return active_stage
        if active_stage in LATE_STAGE_CODES:
            if active_stage == "S7" and question_pack and self._stage_has_pending_questions(
                state=state,
                question_pack=question_pack,
                stage_code="S7",
            ):
                return "S7"
            if active_stage == "S7" and completion_reason:
                return get_next_stage(active_stage) or active_stage
            return active_stage

        if question_pack:
            if self._stage_has_pending_questions(
                state=state,
                question_pack=question_pack,
                stage_code=active_stage,
            ):
                return active_stage
            next_stage = self._resolve_next_pending_stage(
                state=state,
                question_pack=question_pack,
                current_stage=active_stage,
            )
            if next_stage:
                return next_stage
        if active_stage in QUESTION_DRIVEN_STAGE_CODES:
            return get_next_stage(active_stage) or "S7"
        return "S1"
