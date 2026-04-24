from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from ai_hr.services.ten_runtime import TENRuntimeManager


def _build_settings(tmpdir: str) -> SimpleNamespace:
    tmp = Path(tmpdir)
    agent_dir = tmp / "ten_agent"
    session_dir = agent_dir / ".ten_sessions"
    agent_dir.mkdir(parents=True, exist_ok=True)
    session_dir.mkdir(parents=True, exist_ok=True)

    template = {
        "ten": {
            "predefined_graphs": [
                {
                    "name": "ai_hr_interview",
                    "graph": {
                        "nodes": [
                            {
                                "type": "extension",
                                "name": "agora_rtc",
                                "property": {},
                            },
                            {
                                "type": "extension",
                                "name": "interview_orchestrator",
                                "property": {},
                            }
                        ]
                    },
                }
            ]
        }
    }
    template_path = agent_dir / "property.json"
    template_path.write_text(json.dumps(template), encoding="utf-8")

    return SimpleNamespace(
        ai_interview_ten_enabled=True,
        ai_interview_ten_agent_dir=str(agent_dir),
        ai_interview_ten_session_dir=str(session_dir),
        ai_interview_ten_property_template=str(template_path),
        ai_interview_ten_tman_cmd="tman",
        agora_app_id="app-id-123",
        agora_app_certificate="app-cert-123",
        asr_aliyun_appkey=None,
        aliyun_access_key_id=None,
        aliyun_access_key_secret=None,
        tencent_secret_id=None,
        tencent_secret_key=None,
        tencent_region="ap-beijing",
        tts_api_key=None,
        tts_tencent_app_id=None,
    )


def test_prepare_session_should_include_agora_bot_token_when_certificate_enabled() -> None:
    with TemporaryDirectory() as tmpdir:
        settings = _build_settings(tmpdir)
        manager = TENRuntimeManager(settings)

        patch = manager.prepare_session(
            session_id="sess-1",
            candidate_id="cand-1",
            job_id="job-1",
            language="zh-CN",
            rtc={
                "app_id": "app-id-123",
                "channel_name": "room-1",
                "uid": "2002",
                "ten_bot_user_id": "1001",
                "ten_bot_token": "signed-bot-token",
                "metadata": {"ten_bot_token": "fallback-token"},
            },
            payload={},
        )

        property_path = Path(patch["ten_property_file"])
        runtime = json.loads(property_path.read_text(encoding="utf-8"))
        agora_node = runtime["ten"]["predefined_graphs"][0]["graph"]["nodes"][0]

        assert agora_node["name"] == "agora_rtc"
        assert agora_node["property"]["token"] == "signed-bot-token"
        assert agora_node["property"]["app_certificate"] == "app-cert-123"
        assert agora_node["property"]["stream_id"] == 1001
        assert agora_node["property"]["remote_stream_id"] == 2002
        assert agora_node["property"]["user_id"] == "1001"
        assert agora_node["property"]["remote_user_id"] == "2002"

        connections = runtime["ten"]["predefined_graphs"][0]["graph"]["connections"]
        agora_connection = next(item for item in connections if item.get("extension") == "agora_rtc")
        agora_cmds = {
            cmd["name"]: [dest["extension"] for dest in cmd.get("dest", [])]
            for cmd in agora_connection["cmd"]
        }
        assert agora_cmds["on_connected"] == ["interview_orchestrator"]
        assert agora_cmds["on_connection_error"] == ["interview_orchestrator"]
        assert agora_cmds["on_connection_failure"] == ["interview_orchestrator"]
        assert agora_cmds["on_token_expired"] == ["interview_orchestrator"]


def test_prepare_session_should_inject_question_pack_and_company_info() -> None:
    with TemporaryDirectory() as tmpdir:
        settings = _build_settings(tmpdir)
        manager = TENRuntimeManager(settings)

        patch = manager.prepare_session(
            session_id="sess-2",
            candidate_id="cand-2",
            job_id="job-2",
            language="zh-CN",
            rtc={
                "app_id": "app-id-123",
                "channel_name": "room-2",
                "uid": "2003",
                "ten_bot_user_id": "1002",
                "ten_bot_token": "signed-bot-token-2",
            },
            payload={
                "company_info": "我们是一家做企业级 AI 招聘产品的团队。",
                "company_info_source": "payload",
                "company_info_version": "runtime_v1",
                "question_pack": {
                    "questions": [
                        {"question_id": "q1", "question": "请介绍最近一个项目", "stage": "S4"}
                    ],
                    "version": 3,
                },
                "question_pack_source": "runtime_store",
                "question_pack_version": "3",
            },
        )

        property_path = Path(patch["ten_property_file"])
        runtime = json.loads(property_path.read_text(encoding="utf-8"))
        nodes = runtime["ten"]["predefined_graphs"][0]["graph"]["nodes"]
        orchestrator_node = next(node for node in nodes if node["name"] == "interview_orchestrator")

        assert orchestrator_node["property"]["company_info"] == "我们是一家做企业级 AI 招聘产品的团队。"
        assert orchestrator_node["property"]["company_info_source"] == "payload"
        assert orchestrator_node["property"]["company_info_version"] == "runtime_v1"
        assert orchestrator_node["property"]["question_pack_source"] == "runtime_store"
        assert orchestrator_node["property"]["question_pack_version"] == "3"
        assert orchestrator_node["property"]["question_pack"]["questions"][0]["question"] == "请介绍最近一个项目"
