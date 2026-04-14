from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys
import types

from ai_hr.domain.constants import InterviewStage
from ai_hr.services.interview_runtime.question_flow import InterviewQuestionFlowEngine
from ai_hr.services.interview_runtime.question_schema import normalize_question_pack
from ai_hr.services.interview_runtime.runtime_engine import InterviewRuntimeEngine
from ai_hr.services.interview_runtime.stage_progress import StageProgressEngine


def _load_session_context():
    project_root = pathlib.Path(__file__).resolve().parents[1]
    module_path = (
        project_root
        / "ten_agent"
        / "ten_packages"
        / "extension"
        / "interview_orchestrator_python"
        / "session_context.py"
    )
    spec = importlib.util.spec_from_file_location("test_session_context_module", module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["test_session_context_module"] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.SessionContext


def _load_orchestrator_extension():
    project_root = pathlib.Path(__file__).resolve().parents[1]
    module_dir = (
        project_root
        / "ten_agent"
        / "ten_packages"
        / "extension"
        / "interview_orchestrator_python"
    )
    if str(module_dir) not in sys.path:
        sys.path.insert(0, str(module_dir))
    if "ten_runtime" not in sys.modules:
        class _AsyncExtension:
            def __init__(self, name: str):
                self.name = name

        sys.modules["ten_runtime"] = types.SimpleNamespace(
            AsyncExtension=_AsyncExtension,
            AsyncTenEnv=object,
            Cmd=object,
            CmdResult=object,
            Data=object,
            StatusCode=object,
        )
    module_path = module_dir / "main.py"
    spec = importlib.util.spec_from_file_location("test_interview_orchestrator_main", module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["test_interview_orchestrator_main"] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.InterviewOrchestratorExtension


def _question_pack() -> dict:
    return normalize_question_pack(
        {
            "questions": [
                {
                    "question_id": "q-tech-1",
                    "question": "请介绍一下你最近做过的项目，以及你在其中负责的核心模块。",
                    "stage": "S4",
                    "dimension": "project_deep_dive",
                    "expected_signal": "职责,方案,结果",
                    "max_followups": 2,
                },
                {
                    "question_id": "q-tech-2",
                    "question": "你在项目里是怎么做性能优化和问题排查的？",
                    "stage": "S5",
                    "dimension": "experience_validation",
                    "expected_signal": "定位,优化,指标",
                    "max_followups": 1,
                },
            ]
        }
    )


def test_company_question_should_be_deferred_during_technical_stage() -> None:
    InterviewOrchestratorExtension = _load_orchestrator_extension()
    SessionContext = _load_session_context()
    orchestrator = InterviewOrchestratorExtension("interview_orchestrator")
    orchestrator.trace_id = "trace-test"
    orchestrator.session_context = SessionContext(session_id="sess-test")
    orchestrator.flow_engine = InterviewQuestionFlowEngine()
    orchestrator.stage_progress_engine = StageProgressEngine()
    orchestrator.runtime_engine = InterviewRuntimeEngine(
        question_flow_engine=orchestrator.flow_engine,
        stage_progress_engine=orchestrator.stage_progress_engine,
    )
    orchestrator.question_pack = _question_pack()
    orchestrator.state = orchestrator.flow_engine.init_state(question_pack=orchestrator.question_pack)
    orchestrator.state = orchestrator.flow_engine.transition_stage(
        state=orchestrator.state,
        stage_code=InterviewStage.PROJECT_DEEP_DIVE,
        question=orchestrator.flow_engine.current_question(
            state=orchestrator.state,
            question_pack=orchestrator.question_pack,
        ),
    )

    calls: list[str] = []

    async def _fake_send_to_tts(ten_env, text: str, is_final: bool = True, **kwargs):  # noqa: ANN001
        calls.append(text)

    class _FailRuntimeEngine:
        def process_candidate_turn(self, *args, **kwargs):  # noqa: ANN002, ANN003
            raise AssertionError("company question should be deferred before runtime decision")

    orchestrator._send_to_tts = _fake_send_to_tts  # type: ignore[method-assign]
    orchestrator.runtime_engine = _FailRuntimeEngine()  # type: ignore[assignment]

    asyncio.run(
        orchestrator._handle_interaction(
            ten_env=None,  # type: ignore[arg-type]
            transcript="你们公司是做什么业务的？",
            asr_final_ts=0.0,
            asr_sentence_start_ts=0.0,
            asr_physical_stop_ts=0.0,
            orch_receive_ts=0.0,
        )
    )

    assert calls
    assert calls[0] == "公司和岗位相关信息我会在面试最后统一介绍，我们先继续当前面试流程。"
