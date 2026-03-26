from __future__ import annotations

import json
import urllib.error

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_hr.core.config import get_settings
from ai_hr.core.exceptions import AIHRException
from ai_hr.db.base import Base
from ai_hr.db.models import AIDecisionLog, AIModelConfig, AIPromptVersion, AIRequestTrace
from ai_hr.repositories.ai_observability import AIObservabilityRepository
from ai_hr.repositories.ai_runtime import AIRuntimeRepository
from ai_hr.services.llm.client import InvokeContext, LLMClient
from ai_hr.services.llm.guardrails import GuardrailService
from ai_hr.services.llm.router import ModelRoute, ModelRouter
from ai_hr.services.policy.decision import PolicyDecisionService


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
Base.metadata.create_all(bind=engine)


def test_llm_client_mock_invocation_and_observability() -> None:
    with TestingSessionLocal() as session:
        session.add(
            AIModelConfig(
                task_key="resume_parse",
                provider="mock",
                model_name="resume-parse-mock",
                timeout_seconds=5,
                max_retries=1,
                temperature_milli=100,
                is_active=True,
                weight=100,
            )
        )
        session.add(
            AIPromptVersion(
                task_key="resume_parse",
                version="v1",
                system_prompt="mock",
                user_template="mock",
                output_schema={},
                is_active=True,
            )
        )
        session.commit()

        client = LLMClient(
            router=ModelRouter(AIRuntimeRepository(session)),
            guardrail_service=GuardrailService(),
            observability_repository=AIObservabilityRepository(session),
        )
        result = client.invoke_json(
            InvokeContext(
                task_key="resume_parse",
                trace_id="trace-1",
                prompt="5年Python经验，本科，FastAPI项目",
                entity_type="candidate",
                entity_id="cand-1",
            )
        )
        assert result.provider == "mock"
        assert result.task_key == "resume_parse"
        assert "skills" in result.content
        assert result.content["education_level"] == "本科"

        traces = session.execute(select(AIRequestTrace)).scalars().all()
        decisions = session.execute(select(AIDecisionLog)).scalars().all()
        assert len(traces) >= 1
        assert len(decisions) >= 1


def test_policy_decision_handoff_for_low_confidence() -> None:
    service = PolicyDecisionService()
    decision = service.decide_reply_action(confidence=0.4, policy_flags=[])
    assert decision.action == "handoff"
    assert "low_confidence" in decision.policy_flags


class _StubHTTPResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


class _StubStreamingHTTPResponse:
    def __init__(self, lines: list[str]):
        self._lines = [line.encode("utf-8") for line in lines]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def __iter__(self):
        return iter(self._lines)


class _OpenAIRouter:
    def resolve_route(self, task_key: str) -> ModelRoute:
        return ModelRoute(
            provider="openai",
            model_name="deepseek-chat",
            timeout_seconds=8,
            max_retries=0,
            temperature_milli=200,
            prompt_version="v1",
        )


class _MockRouter:
    def resolve_route(self, task_key: str) -> ModelRoute:
        return ModelRoute(
            provider="mock",
            model_name=f"{task_key}-mock",
            timeout_seconds=8,
            max_retries=0,
            temperature_milli=200,
            prompt_version="v1",
        )


def test_interview_followup_text_mode_should_normalize_dict_payload() -> None:
    client = LLMClient(router=_MockRouter())
    result = client.invoke(
        InvokeContext(
            task_key="interview_followup",
            trace_id="trace-text-normalize",
            prompt="test prompt",
            entity_type="session",
            entity_id="s-text-1",
        )
    )
    assert result.fallback_used is False
    assert isinstance(result.content.get("text"), str)
    assert "补充" in result.content.get("text")


def test_llm_client_openai_should_parse_responses_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_HR_LLM_API_KEY", "test-key")
    monkeypatch.setenv("AI_HR_LLM_BASE_URL", "https://api.deepseek.com")

    def _fake_urlopen(request, timeout=None):  # noqa: ANN001
        assert request.full_url.endswith("/v1/responses")
        return _StubHTTPResponse(
            {
                "output_text": json.dumps(
                    {
                        "followup_question": "请补充关键指标。",
                        "reason": "需要量化结果",
                        "policy_flags": [],
                        "confidence": 0.9,
                    },
                    ensure_ascii=False,
                )
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    client = LLMClient(router=_OpenAIRouter())
    result = client.invoke_json(
        InvokeContext(
            task_key="interview_followup",
            trace_id="trace-openai-responses",
            prompt="test prompt",
            entity_type="session",
            entity_id="s-1",
        )
    )
    assert result.fallback_used is False
    assert result.content["followup_question"]


def test_llm_client_openai_should_fallback_to_chat_completions_on_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_HR_LLM_API_KEY", "test-key")
    monkeypatch.setenv("AI_HR_LLM_BASE_URL", "https://api.deepseek.com")
    called_urls: list[str] = []

    def _fake_urlopen(request, timeout=None):  # noqa: ANN001
        called_urls.append(request.full_url)
        if request.full_url.endswith("/v1/responses"):
            raise urllib.error.HTTPError(request.full_url, 404, "Not Found", hdrs=None, fp=None)
        if request.full_url.endswith("/v1/chat/completions"):
            return _StubHTTPResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "followup_question": "请补充方案复盘。",
                                        "reason": "需要追问复盘细节",
                                        "policy_flags": [],
                                        "confidence": 0.88,
                                    },
                                    ensure_ascii=False,
                                )
                            }
                        }
                    ]
                }
            )
        raise AssertionError(f"unexpected url: {request.full_url}")

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    client = LLMClient(router=_OpenAIRouter())
    result = client.invoke_json(
        InvokeContext(
            task_key="interview_followup",
            trace_id="trace-openai-chat-fallback",
            prompt="test prompt",
            entity_type="session",
            entity_id="s-2",
        )
    )
    assert result.fallback_used is False
    assert result.content["followup_question"]
    assert any(url.endswith("/v1/responses") for url in called_urls)
    assert any(url.endswith("/v1/chat/completions") for url in called_urls)


def test_llm_client_openai_stream_should_parse_sse_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_HR_LLM_API_KEY", "test-key")
    monkeypatch.setenv("AI_HR_LLM_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("AI_HR_LLM_STREAMING_ENABLED", "true")
    get_settings.cache_clear()

    def _fake_urlopen(request, timeout=None):  # noqa: ANN001
        assert request.full_url.endswith("/v1/chat/completions")
        return _StubStreamingHTTPResponse(
            [
                'data: {"choices":[{"delta":{"content":"{\\"followup_question\\":\\"请补充指标\\""}}]}\n',
                'data: {"choices":[{"delta":{"content":",\\"reason\\":\\"需要量化\\",\\"policy_flags\\":[] ,\\"confidence\\":0.9}"}}]}\n',
                "data: [DONE]\n",
            ]
        )

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    client = LLMClient(router=_OpenAIRouter())
    deltas: list[str] = []
    result = client.invoke_json(
        InvokeContext(
            task_key="interview_followup",
            trace_id="trace-openai-stream",
            prompt="test prompt",
            entity_type="session",
            entity_id="s-stream",
        ),
        on_text_delta=deltas.append,
    )
    assert result.fallback_used is False
    assert result.content["followup_question"] == "请补充指标"
    assert deltas
    get_settings.cache_clear()


def test_model_router_should_fallback_to_settings_llm_when_runtime_config_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_HR_LLM_PROVIDER", "openai")
    monkeypatch.setenv("AI_HR_LLM_MODEL", "deepseek-chat")
    monkeypatch.setenv("AI_HR_LLM_TIMEOUT_SECONDS", "12")
    monkeypatch.setenv("AI_HR_LLM_MAX_RETRIES", "3")
    get_settings.cache_clear()
    router = ModelRouter(settings=get_settings())
    route = router.resolve_route("interview_followup")
    assert route.provider == "openai"
    assert route.model_name == "deepseek-chat"
    assert route.timeout_seconds == 12
    assert route.max_retries == 3
    assert route.prompt_version == "v1"
    get_settings.cache_clear()


def test_model_router_should_keep_mock_when_settings_provider_is_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_HR_LLM_PROVIDER", "mock")
    monkeypatch.setenv("AI_HR_LLM_MODEL", "ignored-model")
    get_settings.cache_clear()
    router = ModelRouter(settings=get_settings())
    route = router.resolve_route("interview_followup")
    assert route.provider == "mock"
    assert route.model_name == "interview_followup-mock"
    get_settings.cache_clear()


def test_model_router_should_reject_mock_provider_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_HR_ENVIRONMENT", "production")
    monkeypatch.setenv("AI_HR_LLM_PROVIDER", "mock")
    monkeypatch.delenv("AI_HR_LLM_MODEL", raising=False)
    get_settings.cache_clear()
    router = ModelRouter(settings=get_settings())
    with pytest.raises(AIHRException, match="mock provider in production"):
        router.resolve_route("interview_followup")
    get_settings.cache_clear()
