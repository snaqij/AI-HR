from __future__ import annotations

from ai_hr.services.interview_runtime.flow_policy import get_stage_policy
from ai_hr.services.interview_runtime.question_flow import InterviewQuestionFlowEngine


def _sample_pack() -> dict:
    return {
        "questions": [
            {"question": "q1", "stage": "S4", "expected_signal": "职责,结果", "max_followups": 2},
            {"question": "q2", "stage": "S5", "expected_signal": "实习深度", "max_followups": 1},
            {"question": "q3", "stage": "S6", "expected_signal": "排障思路"},
        ]
    }


def test_question_flow_initial_state_contains_stage_metadata() -> None:
    engine = InterviewQuestionFlowEngine()

    state = engine.init_state(question_pack=_sample_pack())

    assert state["interview_stage"] == "S1"
    assert state["interview_stage_name"] == "opening"
    assert state["interview_stage_label"] == "开场确认"
    assert state["stage_goal"]
    assert state["difficulty_level"] == "normal"


def test_question_flow_should_advance_after_sufficient_answer() -> None:
    engine = InterviewQuestionFlowEngine()
    pack = _sample_pack()
    state = engine.init_state(question_pack=pack)
    state = engine.transition_stage(state=state, stage_code="S4", question=engine.current_question(state=state, question_pack=pack))

    evaluation = engine.evaluate_answer(
        transcript="我负责核心接口优化，最终把接口 p95 降了 40%，也补了限流和监控。",
        confidence=0.92,
    )
    updated = engine.apply_turn_result(state=state, evaluation=evaluation, max_followup_per_question=2)

    assert updated["active_question_index"] == 1
    assert updated["completed_questions"] == 1
    assert updated["followup_count_current"] == 0
    assert updated["transition_reason"] == "question_completed"


def test_question_flow_should_followup_when_insufficient_answer() -> None:
    engine = InterviewQuestionFlowEngine()
    pack = _sample_pack()
    state = engine.init_state(question_pack=pack)
    state = engine.transition_stage(state=state, stage_code="S4", question=engine.current_question(state=state, question_pack=pack))

    evaluation = engine.evaluate_answer(transcript="做过优化", confidence=0.9)
    updated = engine.apply_turn_result(state=state, evaluation=evaluation, max_followup_per_question=2)

    assert updated["active_question_index"] == 0
    assert updated["followup_count_current"] == 1
    assert updated["transition_reason"] == "insufficient_detail"


def test_question_flow_should_limit_followup_depth() -> None:
    engine = InterviewQuestionFlowEngine()
    pack = _sample_pack()
    state = engine.init_state(question_pack=pack)
    state = engine.transition_stage(state=state, stage_code="S4", question=engine.current_question(state=state, question_pack=pack))

    for _ in range(3):
        evaluation = engine.evaluate_answer(transcript="有做过", confidence=0.9)
        state = engine.apply_turn_result(state=state, evaluation=evaluation, max_followup_per_question=2)

    assert state["active_question_index"] == 1
    assert state["completed_questions"] >= 1
    assert state["transition_reason"] == "followup_limit_reached"


def test_stage_should_be_derived_to_company_qa_after_pack_exhausted() -> None:
    engine = InterviewQuestionFlowEngine()
    state = engine.init_state(question_pack=_sample_pack())
    state = engine.transition_stage(state=state, stage_code="S6")
    state["question_statuses"] = ["completed", "completed", "completed"]
    state["completed_questions"] = 3
    state["active_question_index"] = 3

    assert engine.derive_stage(state=state) == "S7"


def test_stage_policy_exposes_expected_defaults() -> None:
    policy = get_stage_policy("S4")

    assert policy.name == "project_deep_dive"
    assert policy.max_followups == 2
    assert policy.requires_question_pack is True
