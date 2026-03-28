"""Structured interview question flow engine."""

from __future__ import annotations

from typing import Any


class InterviewQuestionFlowEngine:
    """Manage active question pointer and stage progression."""

    def init_state(self, *, question_pack: dict[str, Any]) -> dict[str, Any]:
        questions = question_pack.get("questions", []) if isinstance(question_pack, dict) else []
        question_count = len(questions) if isinstance(questions, list) else 0
        return {
            "active_question_index": 0,
            "question_statuses": ["pending"] * question_count,
            "followup_count_current": 0,
            "completed_questions": 0,
            "interview_stage": "intro",
        }

    def current_question(self, *, state: dict[str, Any], question_pack: dict[str, Any]) -> dict[str, Any] | None:
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

    def evaluate_answer(self, *, transcript: str, confidence: float | None, min_len: int = 18) -> dict[str, Any]:
        normalized = " ".join((transcript or "").strip().split())
        need_followup = False
        reason = "sufficient"
        if confidence is not None and confidence < 0.60:
            need_followup = True
            reason = "low_confidence"
        elif len(normalized) < max(4, int(min_len)):
            need_followup = True
            reason = "insufficient_detail"
        # Check for repetitive meaningless repetition (e.g. "hello hello hello")
        # If the number of unique words is very low relative to the length
        elif len(set(normalized.split())) <= 2 and len(normalized) > 10:
             need_followup = True
             reason = "repetitive_content"
        return {
            "need_followup": need_followup,
            "reason": reason,
            "normalized_len": len(normalized),
            "confidence": confidence,
        }

    def apply_turn_result(self, *, state: dict[str, Any], evaluation: dict[str, Any], max_followup_per_question: int) -> dict[str, Any]:
        merged = dict(state)
        statuses = list(merged.get("question_statuses", []))
        if not statuses:
            merged["completed_questions"] = 0
            return merged
        idx = max(0, int(merged.get("active_question_index", 0)))
        if idx >= len(statuses):
            merged["completed_questions"] = sum(1 for item in statuses if str(item).startswith("completed"))
            return merged

        need_followup = bool(evaluation.get("need_followup"))
        followup_count = max(0, int(merged.get("followup_count_current", 0)))
        max_followup = max(0, int(max_followup_per_question))
        if need_followup and followup_count < max_followup:
            statuses[idx] = "asked"
            merged["followup_count_current"] = followup_count + 1
        else:
            statuses[idx] = "completed" if not need_followup else "completed_with_gap"
            merged["active_question_index"] = idx + 1
            merged["followup_count_current"] = 0

        merged["question_statuses"] = statuses
        merged["completed_questions"] = sum(1 for item in statuses if str(item).startswith("completed"))
        return merged

    def derive_stage(self, *, state: dict[str, Any]) -> str:
        statuses = list(state.get("question_statuses", []))
        if not statuses:
            return "intro"
        active_idx = max(0, int(state.get("active_question_index", 0)))
        completed = sum(1 for item in statuses if str(item).startswith("completed"))
        total = len(statuses)

        if completed == 0:
            return "intro"
        if completed <= 1:
            return "verification"
        if active_idx < max(2, int(total * 0.6)):
            return "core_questions"
        if active_idx < total:
            return "deep_dive"
        if completed < total:
            return "candidate_questions"
        return "closing"

