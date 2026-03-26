from __future__ import annotations

from ai_hr.services.interview_runtime.question_flow import InterviewQuestionFlowEngine


def _sample_pack() -> dict:
    return {
        "questions": [
            {"question": "q1"},
            {"question": "q2"},
            {"question": "q3"},
        ]
    }


def test_question_flow_should_advance_after_sufficient_answer() -> None:
    engine = InterviewQuestionFlowEngine()
    pack = _sample_pack()
    state = engine.init_state(question_pack=pack)
    evaluation = engine.evaluate_answer(transcript="我负责并完成了服务性能优化，p95下降40%。", confidence=0.92)
    updated = engine.apply_turn_result(state=state, evaluation=evaluation, max_followup_per_question=2)
    assert updated["active_question_index"] == 1
    assert updated["completed_questions"] == 1


def test_question_flow_should_followup_when_insufficient_answer() -> None:
    engine = InterviewQuestionFlowEngine()
    pack = _sample_pack()
    state = engine.init_state(question_pack=pack)
    evaluation = engine.evaluate_answer(transcript="做过优化", confidence=0.9)
    updated = engine.apply_turn_result(state=state, evaluation=evaluation, max_followup_per_question=2)
    assert updated["active_question_index"] == 0
    assert updated["followup_count_current"] == 1


def test_question_flow_should_limit_followup_depth() -> None:
    engine = InterviewQuestionFlowEngine()
    pack = _sample_pack()
    state = engine.init_state(question_pack=pack)
    for _ in range(3):
        evaluation = engine.evaluate_answer(transcript="简答", confidence=0.9)
        state = engine.apply_turn_result(state=state, evaluation=evaluation, max_followup_per_question=2)
    assert state["active_question_index"] == 1
    assert state["completed_questions"] >= 1


def test_stage_should_be_derived_from_question_progress() -> None:
    engine = InterviewQuestionFlowEngine()
    state = engine.init_state(question_pack=_sample_pack())
    assert engine.derive_stage(state=state) == "intro"
    state["question_statuses"][0] = "completed"
    state["completed_questions"] = 1
    state["active_question_index"] = 1
    assert engine.derive_stage(state=state) == "verification"

