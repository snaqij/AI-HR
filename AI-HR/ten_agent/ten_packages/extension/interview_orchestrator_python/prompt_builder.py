from __future__ import annotations

from dataclasses import dataclass

from ai_hr.services.llm.prompts import build_interview_stage_instruction

try:
    from .session_context import SessionContext
except ImportError:  # pragma: no cover
    from session_context import SessionContext


@dataclass(slots=True)
class PromptBuildInput:
    stage: str
    output_mode: str
    candidate_name: str
    transcript: str
    current_question: str
    target_question_id: str
    next_question: str
    success_signals: str
    is_last_followup: bool
    followup_budget_remaining: int
    company_info: str
    stage_goal: str
    missing_evidence: object
    difficulty_level: str
    transition_reason: str
    question_type: str
    focus_experience: str
    focus_module: str
    active_topic_name: str
    active_topic_rounds: int
    must_transition: bool
    candidate_requested_move_on: bool
    flow_reason: str
    system_prompt_prefix: str
    session_context: SessionContext


@dataclass(slots=True)
class PromptBuildResult:
    system_prompt: str
    prompt: str
    instruction: str
    history_text: str
    pending_question: str
    debug_context_payload: dict


class InterviewPromptBuilder:
    def build(self, build_input: PromptBuildInput) -> PromptBuildResult:
        instruction = build_interview_stage_instruction(
            stage=build_input.stage,
            current_question=build_input.current_question,
            expected_signal=build_input.success_signals,
            next_question=build_input.next_question,
            is_last_followup=build_input.is_last_followup,
            company_info=build_input.company_info,
            stage_goal=build_input.stage_goal,
            missing_evidence=build_input.missing_evidence,
            difficulty_level=build_input.difficulty_level,
            transition_reason=build_input.transition_reason,
            question_type=build_input.question_type,
            focus_experience=build_input.focus_experience,
            focus_module=build_input.focus_module,
            active_topic_name=build_input.active_topic_name,
            active_topic_rounds=build_input.active_topic_rounds,
            must_transition=build_input.must_transition,
            candidate_requested_move_on=build_input.candidate_requested_move_on,
            flow_reason=build_input.flow_reason,
        )
        history_text = build_input.session_context.build_recent_history_text()
        pending_question = build_input.session_context.get_last_assistant_question() or build_input.current_question

        prompt = (
            "### Interview Context ###\n"
            f"Current stage: {build_input.stage}\n"
            f"Output mode: {build_input.output_mode}\n"
            f"Candidate: {build_input.candidate_name}\n\n"
            "### Interviewer Instruction ###\n"
            f"{instruction}\n\n"
            "### Orchestration State ###\n"
            f"Target question id: {build_input.target_question_id or 'unknown'}\n"
            f"Question type: {build_input.question_type or 'unknown'}\n"
            f"Focus experience: {build_input.focus_experience or 'not_locked'}\n"
            f"Focus module: {build_input.focus_module or 'not_locked'}\n"
            f"Active topic: {build_input.active_topic_name or 'unnamed'}\n"
            f"Active topic rounds: {build_input.active_topic_rounds}\n"
            f"Follow-up budget remaining: {max(0, int(build_input.followup_budget_remaining or 0))}\n"
            f"Must transition now: {'yes' if build_input.must_transition else 'no'}\n"
            f"Candidate requested move on: {'yes' if build_input.candidate_requested_move_on else 'no'}\n"
            f"Flow reason: {build_input.flow_reason or build_input.transition_reason or 'n/a'}\n\n"
            f"{history_text}"
            "### Current Turn ###\n"
            f"Last assistant question: {pending_question}\n"
            f"Candidate final answer: {build_input.transcript}\n\n"
            "Continue from the recent stable dialogue and the current turn."
            " Do not ignore what the candidate already answered,"
            " and do not repeat the previous question."
            " You are only generating one concise follow-up question."
            " Do not rewrite or restate the main scripted question.\n\n"
            "### Candidate Response (Volatile Output) ###\n"
            f"\"{build_input.transcript}\""
        )

        return PromptBuildResult(
            system_prompt=build_input.system_prompt_prefix,
            prompt=prompt,
            instruction=instruction,
            history_text=history_text,
            pending_question=pending_question,
            debug_context_payload={
                "stage": build_input.stage,
                "output_mode": build_input.output_mode,
                "candidate_name": build_input.candidate_name,
                "pending_question": pending_question,
                "current_transcript": build_input.transcript,
                "target_question_id": build_input.target_question_id,
                "followup_budget_remaining": build_input.followup_budget_remaining,
                "question_type": build_input.question_type,
                "focus_experience": build_input.focus_experience,
                "focus_module": build_input.focus_module,
                "active_topic_name": build_input.active_topic_name,
                "active_topic_rounds": build_input.active_topic_rounds,
                "must_transition": build_input.must_transition,
                "candidate_requested_move_on": build_input.candidate_requested_move_on,
                "flow_reason": build_input.flow_reason,
                "recent_turns_count": len(build_input.session_context.recent_turns),
                "recent_turns_preview": [
                    {
                        "role": turn.role,
                        "stage": turn.stage,
                        "text": turn.text,
                    }
                    for turn in build_input.session_context.recent_turns[-build_input.session_context.max_turns :]
                ],
                "instruction_preview": instruction[:500],
                "prompt_preview": prompt[:1200],
            },
        )
