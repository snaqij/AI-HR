"""统一 LLM 调用客户端。"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Callable

import httpx

logger = logging.getLogger(__name__)

from ...repositories.ai_observability import AIObservabilityRepository
from ...core.config import get_settings
from ...schemas.ai_llm import LLMInvokeResult
from .contracts import (
    CandidateScoreLLMOutput,
    IntentClassifyLLMOutput,
    InterviewFollowupLLMOutput,
    InterviewQuestionSetLLMOutput,
    ReplyGenerateLLMOutput,
    ResumeParseLLMOutput,
)
from .guardrails import GuardrailService
from .router import ModelRoute, ModelRouter


@dataclass(slots=True)
class InvokeContext:
    """LLM 调用上下文。"""

    task_key: str
    trace_id: str
    prompt: str
    entity_type: str
    entity_id: str


class LLMClient:
    """提供统一 LLM 调用、校验与追踪能力。"""

    def __init__(
        self,
        *,
        router: ModelRouter,
        guardrail_service: GuardrailService | None = None,
        observability_repository: AIObservabilityRepository | None = None,
    ):
        """初始化依赖组件。"""
        self._router = router
        self._guardrail = guardrail_service or GuardrailService()
        self._observability = observability_repository
        self._settings = get_settings()
        self._responses_api_unsupported_hosts: set[str] = set()
        
        # Persistent HTTPX Client for Connection Pooling (Keep-Alive)
        self._session = httpx.Client(
            timeout=httpx.Timeout(10.0, connect=5.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10, keepalive_expiry=5.0),
            follow_redirects=True
        )

    def invoke_json(
        self,
        context: InvokeContext,
        *,
        on_text_delta: Callable[[str], None] | None = None,
        write_observability: bool = True,
    ) -> LLMInvokeResult:
        """按任务调用模型并返回结构化结果。"""
        return self._invoke_core(context, on_text_delta=on_text_delta, write_observability=write_observability, mode="json")

    def invoke(
        self,
        context: InvokeContext,
        *,
        on_text_delta: Callable[[str], None] | None = None,
        write_observability: bool = True,
    ) -> LLMInvokeResult:
        """调用模型并返回纯文本结果。"""
        return self._invoke_core(context, on_text_delta=on_text_delta, write_observability=write_observability, mode="text")

    def stream_invoke(
        self,
        context: InvokeContext,
        *,
        on_text_delta: Callable[[str], None] | None = None,
        write_observability: bool = True,
    ) -> Iterable[str]:
        """流式调用模型并返回 delta 迭代器。"""
        # This is a bit tricky because we want to yield deltas but also record observability at the end.
        # We wrap the internal provider stream.
        route = self._router.resolve_route(context.task_key)
        sanitized_prompt = self._guardrail.sanitize_input(context.prompt)
        request_hash = hashlib.sha256(sanitized_prompt.encode("utf-8")).hexdigest()
        
        start = time.perf_counter()
        full_text_collector = []
        
        def _internal_delta_handler(delta: str) -> None:
            full_text_collector.append(delta)
            if on_text_delta:
                on_text_delta(delta)

        # Note: In a real implementation, _invoke_provider would be a generator if streaming.
        # Here we rely on the callback for now, but to make it a true generator for the caller:
        if route.provider == "openai":
            # Direct yield from stream
            yield from self._yield_openai_stream(
                route=route,
                prompt=sanitized_prompt,
                on_text_delta=_internal_delta_handler
            )
        elif route.provider == "mock":
            # Simulate streaming
            mock_res = self._invoke_mock(task_key=context.task_key, prompt=sanitized_prompt)
            text = self._normalize_text_payload(task_key=context.task_key, raw_payload=mock_res)
            # Yield in small chunks to simulate network
            chunk_size = 4
            for i in range(0, len(text), chunk_size):
                chunk = text[i:i+chunk_size]
                _internal_delta_handler(chunk)
                yield chunk
                time.sleep(0.02)
        else:
            # Fallback for other providers (as blocks)
            raw = self._invoke_provider(route=route, task_key=context.task_key, prompt=sanitized_prompt, mode="text")
            text = self._normalize_text_payload(task_key=context.task_key, raw_payload=raw)
            _internal_delta_handler(text)
            yield text

        # Post-stream Observability
        latency_ms = int((time.perf_counter() - start) * 1000)
        if write_observability and self._observability:
            full_text = "".join(full_text_collector)
            self._observability.create_trace(
                trace_id=context.trace_id,
                task_key=context.task_key,
                provider=route.provider,
                model_name=route.model_name,
                prompt_version=route.prompt_version,
                request_hash=request_hash,
                response_status="success",
                latency_ms=latency_ms,
                retry_count=0,
                fallback_used=False,
            )
            self._observability.create_decision_log(
                trace_id=context.trace_id,
                module_key=context.task_key,
                entity_type=context.entity_type,
                entity_id=context.entity_id,
                action="success",
                confidence=0.9, # Stream mode default confidence
                risk_tags=[],
                policy_flags=[],
                input_summary=sanitized_prompt[:200],
                output_summary=full_text[:500],
                provider=route.provider,
                model_name=route.model_name,
                prompt_version=route.prompt_version,
            )

    def _invoke_core(
        self,
        context: InvokeContext,
        *,
        on_text_delta: Callable[[str], None] | None = None,
        write_observability: bool = True,
        mode: str = "json",
    ) -> LLMInvokeResult:
        """核心调用逻辑。"""
        route = self._router.resolve_route(context.task_key)
        sanitized_prompt = self._guardrail.sanitize_input(context.prompt)
        request_hash = hashlib.sha256(sanitized_prompt.encode("utf-8")).hexdigest()

        start = time.perf_counter()
        retry_count = 0
        response_payload: Any = None
        status = "success"
        fallback_used = False
        while retry_count <= route.max_retries:
            try:
                raw_payload = self._invoke_provider(
                    route=route,
                    task_key=context.task_key,
                    prompt=sanitized_prompt,
                    on_text_delta=on_text_delta,
                    mode=mode,
                )
                if mode == "json":
                    response_payload = self._validate_contract(context.task_key, raw_payload)
                    valid, flags = self._guardrail.validate_output(task_key=context.task_key, payload=response_payload)
                    if not valid:
                        response_payload["policy_flags"] = list(set((response_payload.get("policy_flags") or []) + flags))
                        status = "guardrail_blocked"
                else:
                    response_payload = self._normalize_text_payload(task_key=context.task_key, raw_payload=raw_payload)
                break
            except Exception as e:
                logger.error(f"LLM Client Attempt {retry_count} failed: {e}", exc_info=True)
                retry_count += 1
                if retry_count > route.max_retries:
                    status = "failed"
                    fallback_used = True
                    response_payload = {"error": "llm_failed", "policy_flags": ["llm_failed"]} if mode == "json" else "llm_failed"
                    break

        latency_ms = int((time.perf_counter() - start) * 1000)
        result = LLMInvokeResult(
            trace_id=context.trace_id,
            task_key=context.task_key,
            provider=route.provider,
            model_name=route.model_name,
            prompt_version=route.prompt_version,
            content=response_payload if mode == "json" else {"text": response_payload},
            latency_ms=latency_ms,
            retry_count=retry_count,
            fallback_used=fallback_used,
        )

        if write_observability and self._observability is not None:
            self._observability.create_trace(
                trace_id=context.trace_id,
                task_key=context.task_key,
                provider=route.provider,
                model_name=route.model_name,
                prompt_version=route.prompt_version,
                request_hash=request_hash,
                response_status=status,
                latency_ms=latency_ms,
                retry_count=retry_count,
                fallback_used=fallback_used,
            )
            self._observability.create_decision_log(
                trace_id=context.trace_id,
                module_key=context.task_key,
                entity_type=context.entity_type,
                entity_id=context.entity_id,
                action="fallback" if fallback_used else "success",
                confidence=(response_payload or {}).get("confidence") if mode == "json" else None,
                risk_tags=(response_payload or {}).get("risk_tags") or [] if mode == "json" else [],
                policy_flags=(response_payload or {}).get("policy_flags") or [] if mode == "json" else [],
                input_summary=sanitized_prompt[:200],
                output_summary=str(response_payload)[:500],
                provider=route.provider,
                model_name=route.model_name,
                prompt_version=route.prompt_version,
            )
        return result

    def _invoke_provider(
        self,
        *,
        route: ModelRoute,
        task_key: str,
        prompt: str,
        on_text_delta: Callable[[str], None] | None = None,
        mode: str = "json",
    ) -> Any:
        """调用具体 provider。当前默认 mock。"""
        if route.provider == "mock":
            return self._invoke_mock(task_key=task_key, prompt=prompt)
        if route.provider == "openai":
            return self._invoke_openai(route=route, prompt=prompt, on_text_delta=on_text_delta, mode=mode)
        raise RuntimeError(f"Provider '{route.provider}' is not configured")

    def _normalize_text_payload(self, *, task_key: str, raw_payload: Any) -> str:
        """Normalize provider payload into plain text for mode='text'."""
        if isinstance(raw_payload, str):
            return raw_payload
        if isinstance(raw_payload, dict):
            if task_key == "interview_followup":
                if raw_payload.get("followup_question"):
                    return str(raw_payload.get("followup_question"))
            for key in ("text", "output_text", "reply_text", "content"):
                value = raw_payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value
            return json.dumps(raw_payload, ensure_ascii=False)
        if isinstance(raw_payload, list):
            merged = [str(item).strip() for item in raw_payload if str(item).strip()]
            return " ".join(merged)
        if raw_payload is None:
            return ""
        return str(raw_payload)

    def _validate_contract(self, task_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        """根据任务类型执行契约校验。"""
        if task_key == "resume_parse":
            return ResumeParseLLMOutput.model_validate(payload).model_dump()
        if task_key == "candidate_score":
            return CandidateScoreLLMOutput.model_validate(payload).model_dump()
        if task_key == "intent_classify":
            return IntentClassifyLLMOutput.model_validate(payload).model_dump()
        if task_key == "reply_generate":
            return ReplyGenerateLLMOutput.model_validate(payload).model_dump()
        if task_key == "interview_question_set":
            return InterviewQuestionSetLLMOutput.model_validate(payload).model_dump()
        if task_key == "interview_followup":
            return InterviewFollowupLLMOutput.model_validate(payload).model_dump()
        return payload

    def _invoke_mock(self, *, task_key: str, prompt: str) -> dict[str, Any]:
        """Mock Provider：离线测试场景下提供确定性输出。"""
        lower = prompt.lower()
        if task_key == "resume_parse":
            skills = []
            for token in ("python", "fastapi", "mysql", "java", "golang", "kubernetes"):
                if token in lower:
                    skills.append(token)
            years_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:年|years?)", prompt, re.IGNORECASE)
            years = float(years_match.group(1)) if years_match else None
            education = None
            if "本科" in prompt or "bachelor" in lower:
                education = "本科"
            elif "硕士" in prompt or "master" in lower:
                education = "硕士"
            risks = []
            if not skills:
                risks.append("skills_missing")
            return {
                "skills": skills,
                "experience_years": years,
                "education_level": education,
                "projects": [],
                "confidence": 0.82 if skills else 0.58,
                "risk_tags": risks,
            }
        if task_key == "candidate_score":
            base = 70.0
            if "python" in lower:
                base += 10
            if "fastapi" in lower:
                base += 8
            if "mysql" in lower:
                base += 6
            total_score = min(base, 98.0)
            return {
                "dimension_scores": {
                    "skills_match": min(100.0, total_score + 2),
                    "experience_relevance": min(100.0, total_score - 3),
                    "stability": 72.0,
                    "project_relevance": 68.0,
                },
                "total_score": total_score,
                "explanation": "mock llm scoring output",
                "risk_tags": [] if total_score >= 75 else ["skills_match_low"],
            }
        if task_key == "intent_classify":
            if any(keyword in lower for keyword in ("薪资", "salary", "package")):
                return {"intent": "salary", "confidence": 0.58, "policy_flags": ["need_human_review"]}
            if any(keyword in lower for keyword in ("你好", "hello", "hi")):
                return {"intent": "greeting", "confidence": 0.94, "policy_flags": []}
            return {"intent": "general", "confidence": 0.75, "policy_flags": []}
        if task_key == "reply_generate":
            samples = [
                "收到你的消息，我们会尽快和你确认后续安排。",
                "感谢反馈，下一步流程我这边先为你登记。",
                "好的，相关信息已记录，稍后会同步具体时间。",
            ]
            reply_text = samples[random.randint(0, len(samples) - 1)]
            return {"reply_text": reply_text, "confidence": 0.82, "policy_flags": []}
        if task_key == "interview_question_set":
            return {
                "questions": [
                    {
                        "question": "请介绍一个你主导的项目，并说明可量化结果。",
                        "dimension": "project_experience",
                        "expected_signal": "目标、行动、结果完整闭环",
                        "followup_condition": "若结果不可量化则追问指标",
                    },
                    {
                        "question": "面对线上故障你如何定位并快速恢复？",
                        "dimension": "problem_solving",
                        "expected_signal": "排障路径清晰且有止损策略",
                        "followup_condition": "若无步骤细节则追问",
                    },
                ],
                "confidence": 0.86,
                "policy_flags": [],
            }
        if task_key == "interview_followup":
            return {
                "followup_question": "你刚提到系统优化，请补充一项具体性能指标提升幅度。",
                "reason": "需要量化证据验证贡献度",
                "policy_flags": [],
                "confidence": 0.84,
            }
        return {}

    def _invoke_openai(
        self,
        *,
        route: ModelRoute,
        prompt: str,
        on_text_delta: Callable[[str], None] | None = None,
        mode: str = "json",
    ) -> Any:
        """OpenAI-compatible provider: prefer Responses API, fallback to Chat Completions."""
        import os

        api_key = (self._settings.llm_api_key or os.getenv("AI_HR_LLM_API_KEY") or "").strip()
        if not api_key:
            raise RuntimeError("AI_HR_LLM_API_KEY is required for openai provider")
        base_url = (
            (self._settings.llm_base_url or os.getenv("AI_HR_LLM_BASE_URL") or "https://api.openai.com").strip()
        ).rstrip("/")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        host = urllib.parse.urlparse(base_url).netloc.lower()
        responses_supported = host not in self._responses_api_unsupported_hosts
        should_stream = self._settings.llm_streaming_enabled and on_text_delta is not None
        if should_stream:
            try:
                return self._invoke_openai_stream(
                    route=route,
                    prompt=prompt,
                    base_url=base_url,
                    headers=headers,
                    on_text_delta=on_text_delta,
                    mode=mode,
                )
            except Exception:
                # If we already know responses API is not supported for this host,
                # avoid an extra round-trip and fallback directly.
                if not responses_supported:
                    return self._invoke_openai_chat_completions(
                        route=route,
                        prompt=prompt,
                        base_url=base_url,
                        headers=headers,
                        mode=mode,
                    )
                pass

        if not responses_supported:
            return self._invoke_openai_chat_completions(
                route=route,
                prompt=prompt,
                base_url=base_url,
                headers=headers,
                mode=mode,
            )

        responses_body = {
            "model": route.model_name,
            "input": prompt,
            "temperature": round(route.temperature_milli / 1000, 3),
        }
        if mode == "json":
            responses_body["text"] = {"format": {"type": "json_object"}}
        try:
            responses_payload = self._post_json(
                url=f"{base_url}/v1/responses",
                request_body=responses_body,
                headers=headers,
                timeout_seconds=route.timeout_seconds,
            )
            responses_text = self._extract_responses_text(responses_payload)
            if not responses_text:
                raise RuntimeError("openai_empty_responses_output")
            return self._parse_json_text(responses_text) if mode == "json" else responses_text
        except urllib.error.HTTPError as exc:
            # Some OpenAI-compatible gateways do not support Responses API.
            if exc.code not in {404, 405}:
                raise RuntimeError(f"openai_http_error:{exc.code}") from exc
            self._responses_api_unsupported_hosts.add(host)
        except Exception:
            if should_stream:
                # Streaming already failed and responses also failed: continue to chat fallback.
                pass
            else:
                # Non-streaming mode should preserve compatibility via chat completion fallback.
                pass

        return self._invoke_openai_chat_completions(
            route=route,
            prompt=prompt,
            base_url=base_url,
            headers=headers,
            mode=mode,
        )

    def _invoke_openai_chat_completions(
        self,
        *,
        route: ModelRoute,
        prompt: str,
        base_url: str,
        headers: dict[str, str],
        mode: str = "json",
    ) -> Any:
        chat_body = {
            "model": route.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": round(route.temperature_milli / 1000, 3),
        }
        if mode == "json":
            chat_body["response_format"] = {"type": "json_object"}
        try:
            payload = self._post_json(
                url=f"{base_url}/v1/chat/completions",
                request_body=chat_body,
                headers=headers,
                timeout_seconds=route.timeout_seconds,
            )
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"openai_http_error:{exc.code}") from exc
        except Exception as exc:
            raise RuntimeError(f"openai_error:{exc}") from exc

        text_blob = self._extract_chat_completions_text(payload)
        if not text_blob:
            raise RuntimeError("openai_empty_output")
        return self._parse_json_text(text_blob) if mode == "json" else text_blob

    def _yield_openai_stream(
        self,
        *,
        route: ModelRoute,
        prompt: str,
        on_text_delta: Callable[[str], None] | None = None,
    ) -> Iterable[str]:
        """Internal generator for OpenAI stream."""
        import os
        api_key = (self._settings.llm_api_key or os.getenv("AI_HR_LLM_API_KEY") or "").strip()
        base_url = (self._settings.llm_base_url or os.getenv("AI_HR_LLM_BASE_URL") or "https://api.openai.com").strip().rstrip("/")
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        
        chat_body = {
            "model": route.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": round(route.temperature_milli / 1000, 3),
            "stream": True,
        }
        
        for attempt in range(2):
            try:
                url = f"{base_url}/v1/chat/completions"
                with self._session.stream("POST", url, json=chat_body, headers=headers, timeout=max(1, route.timeout_seconds)) as resp:
                    resp.raise_for_status()
                    for line in resp.iter_lines():
                        if not line: continue
                        line = line.strip()
                        if not line or not line.startswith("data:"): continue
                        body = line[5:].strip()
                        if body == "[DONE]": break
                        try:
                            payload = json.loads(body)
                            delta_text = self._extract_stream_delta_text(payload)
                            if delta_text:
                                if on_text_delta: on_text_delta(delta_text)
                                yield delta_text
                        except Exception:
                            continue
                return  # 正常完成，退出生成器
            except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError) as exc:
                if attempt == 0:
                    logger.warning(f"LLM Stream connection error (likely stale keep-alive), retrying: {exc}")
                    continue
                logger.error(f"LLM Stream Yield Error after retry: {exc}", exc_info=True)
                raise
            except Exception as exc:
                logger.error(f"LLM Stream Yield Error: {exc}", exc_info=True)
                raise


    def _invoke_openai_stream(
        self,
        *,
        route: ModelRoute,
        prompt: str,
        base_url: str,
        headers: dict[str, str],
        on_text_delta: Callable[[str], None] | None = None,
        mode: str = "json",
    ) -> Any:
        chat_body = {
            "model": route.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": round(route.temperature_milli / 1000, 3),
            "stream": True,
        }
        if mode == "json":
            chat_body["response_format"] = {"type": "json_object"}
        req = urllib.request.Request(
            url=f"{base_url}/v1/chat/completions",
            method="POST",
            data=json.dumps(chat_body).encode("utf-8"),
            headers=headers,
        )
        text_parts: list[str] = []
        try:
            with urllib.request.urlopen(req, timeout=max(1, route.timeout_seconds)) as resp:
                for line_bytes in resp:
                    if not line_bytes:
                        continue
                    line = line_bytes.decode("utf-8").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    body = line[5:].strip()
                    if body == "[DONE]":
                        break
                    try:
                        payload = json.loads(body)
                        delta_text = self._extract_stream_delta_text(payload)
                        if delta_text:
                            text_parts.append(delta_text)
                            if on_text_delta is not None:
                                on_text_delta(delta_text)
                    except Exception:
                        continue
        except Exception as exc:
            import logging
            logging.getLogger("ai_hr.llm").error(f"LLM Stream Error: {exc}", exc_info=True)
            raise

        full_text = "".join(text_parts).strip()
        if not full_text:
            raise RuntimeError("openai_empty_stream_output")
        return self._parse_json_text(full_text) if mode == "json" else full_text

    def _post_json(
        self,
        *,
        url: str,
        request_body: dict[str, Any],
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> dict[str, Any]:
        resp = self._session.post(
            url=url,
            json=request_body,
            headers=headers,
            timeout=max(1, timeout_seconds)
        )
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _extract_responses_text(payload: dict[str, Any]) -> str:
        output_text = payload.get("output_text")
        if isinstance(output_text, str):
            return output_text
        output = payload.get("output")
        if isinstance(output, list):
            parts: list[str] = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    if isinstance(block, dict) and isinstance(block.get("text"), str):
                        parts.append(block["text"])
            return "".join(parts).strip()
        return ""

    @staticmethod
    def _extract_chat_completions_text(payload: dict[str, Any]) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        first_choice = choices[0] if isinstance(choices[0], dict) else {}
        message = first_choice.get("message")
        if not isinstance(message, dict):
            return ""
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    return item["text"]
        return ""

    @staticmethod
    def _extract_stream_delta_text(payload: dict[str, Any]) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        first_choice = choices[0] if isinstance(choices[0], dict) else {}
        delta = first_choice.get("delta")
        if not isinstance(delta, dict):
            return ""
        content = delta.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
            return "".join(parts)
        return ""

    @staticmethod
    def _parse_json_text(text: str) -> dict[str, Any]:
        normalized = text.strip()
        if normalized.startswith("```"):
            normalized = normalized.strip("`")
            normalized = normalized.removeprefix("json").strip()
        try:
            payload = json.loads(normalized)
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass

        match = re.search(r"\{[\s\S]*\}", normalized)
        if not match:
            raise RuntimeError("openai_invalid_json_output")
        payload = json.loads(match.group(0))
        if not isinstance(payload, dict):
            raise RuntimeError("openai_invalid_json_output")
        return payload
