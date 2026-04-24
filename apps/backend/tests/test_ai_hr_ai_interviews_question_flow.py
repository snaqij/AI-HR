from __future__ import annotations

from ai_hr.services.interview_runtime.flow_policy import get_stage_policy
from ai_hr.services.interview_runtime.question_flow import InterviewQuestionFlowEngine
from ai_hr.services.interview_runtime.runtime_engine import InterviewRuntimeEngine


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
    state = engine.transition_stage(
        state=state,
        stage_code="S4",
        question=engine.current_question(state=state, question_pack=pack),
    )

    evaluation = engine.evaluate_answer(
        transcript="我负责核心接口优化，最终把接口 p95 延迟降低了 40%，也补了限流和监控。",
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
    state = engine.transition_stage(
        state=state,
        stage_code="S4",
        question=engine.current_question(state=state, question_pack=pack),
    )

    evaluation = engine.evaluate_answer(transcript="做过优化", confidence=0.9)
    updated = engine.apply_turn_result(state=state, evaluation=evaluation, max_followup_per_question=2)

    assert updated["active_question_index"] == 0
    assert updated["followup_count_current"] == 1
    assert updated["transition_reason"] == "insufficient_detail"
    assert updated["current_question_status"] == "scripted_asked"
    assert updated["current_output_mode"] == "llm_followup"
    assert updated["current_question_asked"] is True


def test_question_flow_should_limit_followup_depth() -> None:
    engine = InterviewQuestionFlowEngine()
    pack = _sample_pack()
    state = engine.init_state(question_pack=pack)
    state = engine.transition_stage(
        state=state,
        stage_code="S4",
        question=engine.current_question(state=state, question_pack=pack),
    )

    for _ in range(3):
        evaluation = engine.evaluate_answer(transcript="有做过", confidence=0.9)
        state = engine.apply_turn_result(state=state, evaluation=evaluation, max_followup_per_question=2)

    assert state["active_question_index"] == 1
    assert state["completed_questions"] >= 1
    assert state["transition_reason"] == "followup_limit_reached"
    assert state["current_question_status"] == "completed_with_gap"


def test_runtime_engine_should_request_llm_followup_for_insufficient_answer() -> None:
    flow = InterviewQuestionFlowEngine()
    runtime = InterviewRuntimeEngine(question_flow_engine=flow)
    pack = _sample_pack()
    state = flow.init_state(question_pack=pack)
    state = flow.transition_stage(
        state=state,
        stage_code="S4",
        question=flow.current_question(state=state, question_pack=pack),
    )

    decision = runtime.process_candidate_turn(
        state=state,
        question_pack=pack,
        transcript="做过一点优化",
        confidence=0.95,
    )

    assert decision.output_mode == "llm_followup"
    assert decision.must_transition is False
    assert decision.target_question is not None
    assert decision.target_question["question"] == "q1"
    assert decision.followup_budget_remaining >= 0


def test_runtime_engine_should_switch_to_next_scripted_question_after_completion() -> None:
    flow = InterviewQuestionFlowEngine()
    runtime = InterviewRuntimeEngine(question_flow_engine=flow)
    pack = _sample_pack()
    state = flow.init_state(question_pack=pack)
    state = flow.transition_stage(
        state=state,
        stage_code="S4",
        question=flow.current_question(state=state, question_pack=pack),
    )

    decision = runtime.process_candidate_turn(
        state=state,
        question_pack=pack,
        transcript="我负责核心接口优化，并给出了明确指标、方案和结果。",
        confidence=0.95,
    )

    assert decision.output_mode == "scripted_question"
    assert decision.must_transition is True
    assert decision.target_question is not None
    assert decision.target_question["question"] == "q2"
    assert decision.updated_state["active_question_index"] == 1
    assert decision.updated_state["current_question_asked"] is False
    assert decision.updated_state["current_question_status"] == "pending"
    assert decision.updated_state["current_output_mode"] == "scripted_question"


def test_stage_should_be_derived_to_company_qa_after_pack_exhausted() -> None:
    engine = InterviewQuestionFlowEngine()
    state = engine.init_state(question_pack=_sample_pack())
    state = engine.transition_stage(state=state, stage_code="S6")
    state["question_statuses"] = ["completed", "completed", "completed"]
    state["completed_questions"] = 3
    state["active_question_index"] = 3

    assert engine.derive_stage(state=state, question_pack=_sample_pack()) == "S7"


def test_question_flow_should_follow_stage_priority_before_global_order() -> None:
    engine = InterviewQuestionFlowEngine()
    pack = {
        "questions": [
            {"idx": 1, "question": "intro", "stage": "S2", "max_followups": 1},
            {"idx": 2, "question": "s3-q1", "stage": "S3", "max_followups": 2},
            {"idx": 3, "question": "s3-q2", "stage": "S3", "max_followups": 2},
            {"idx": 4, "question": "s4-q1", "stage": "S4", "max_followups": 2},
            {"idx": 5, "question": "company", "stage": "S7", "max_followups": 1},
            {"idx": 6, "question": "s3-q3", "stage": "S3", "max_followups": 2},
        ]
    }
    state = engine.init_state(question_pack=pack)
    state = engine.transition_stage(state=state, stage_code="S2")

    expected_sequence = [
        ("intro", "S2"),
        ("s3-q1", "S3"),
        ("s3-q2", "S3"),
        ("s3-q3", "S3"),
        ("s4-q1", "S4"),
        ("company", "S7"),
    ]

    for expected_question, expected_stage in expected_sequence:
        current = engine.current_question(state=state, question_pack=pack)
        assert current is not None
        assert current["question"] == expected_question
        assert state["interview_stage"] == expected_stage
        state = engine.apply_turn_result(
            state=state,
            evaluation={"need_followup": False, "reason": "question_completed"},
            question_pack=pack,
            current_q_max_followups=current.get("max_followups"),
        )

    assert engine.current_question(state=state, question_pack=pack) is None
    assert state["interview_stage"] == "S8"


def test_question_schema_should_sort_by_explicit_idx() -> None:
    from ai_hr.services.interview_runtime.question_schema import normalize_question_pack

    pack = normalize_question_pack(
        {
            "questions": [
                {"idx": 3, "question": "q3", "stage": "S3"},
                {"idx": 1, "question": "q1", "stage": "S2"},
                {"idx": 2, "question": "q2", "stage": "S3"},
            ]
        }
    )

    assert [item["question"] for item in pack["questions"]] == ["q1", "q2", "q3"]


def test_stage_policy_exposes_expected_defaults() -> None:
    policy = get_stage_policy("S4")

    assert policy.name == "project_deep_dive"
    assert policy.max_followups == 2
    assert policy.requires_question_pack is True
