"""Unified LLM client."""

from __future__ import annotations

import hashlib
import json
import logging
import random
import re
import time
import asyncio
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, AsyncIterator

import httpx
from ...repositories.ai_observability import AIObservabilityRepository
from ...core.config import get_settings
from ...schemas.ai_llm import LLMInvokeResult
from .contracts import (
    CandidateEvaluationLLMOutput,
    CandidateScoreLLMOutput,
    IntentClassifyLLMOutput,
    InterviewFollowupLLMOutput,
    InterviewQuestionSetLLMOutput,
    ReplyGenerateLLMOutput,
    ResumeParseLLMOutput,
)
from .guardrails import GuardrailService
from .router import ModelRoute, ModelRouter

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class InvokeContext:
    """LLM invocation context."""

    task_key: str
    trace_id: str
    prompt: str
    system_prompt: str = ""
    entity_type: str = "candidate"
    entity_id: str = "default_user"


class LLMClient:
    """Provides unified LLM invocation, validation, and observability."""

    def __init__(
        self,
        *,
        router: ModelRouter,
        guardrail_service: GuardrailService | None = None,
        observability_repository: AIObservabilityRepository | None = None,
    ):
        """Initialize dependencies."""
        self._router = router
        self._guardrail = guardrail_service or GuardrailService()
        self._observability = observability_repository
        self._settings = get_settings()
        self._responses_api_unsupported_hosts: set[str] = set()
        
        # Optimized for voice conversations: keep connection alive for 60s to cover candidate speech duration.
        self._session = httpx.Client(
            timeout=httpx.Timeout(10.0, connect=5.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10, keepalive_expiry=60.0),
            follow_redirects=True
        )
        self._async_session = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10, keepalive_expiry=60.0),
            follow_redirects=True
        )

    def invoke_json(
        self,
        context: InvokeContext,
        *,
        on_text_delta: Callable[[str], None] | None = None,
        write_observability: bool = True,
    ) -> LLMInvokeResult:
        """Invoke model and return structured JSON content."""
        return self._invoke_core(context, on_text_delta=on_text_delta, write_observability=write_observability, mode="json")

    def invoke(
        self,
        context: InvokeContext,
        *,
        on_text_delta: Callable[[str], None] | None = None,
        write_observability: bool = True,
    ) -> LLMInvokeResult:
        """Invoke model and return plain text content."""
        return self._invoke_core(context, on_text_delta=on_text_delta, write_observability=write_observability, mode="text")

    async def async_stream_invoke(
        self,
        context: InvokeContext,
        *,
        on_text_delta: Callable[[str], None] | None = None,
        write_observability: bool = True,
    ) -> AsyncIterator[str]:
        """Invoke model in async streaming mode and yield text deltas."""
        route = self._router.resolve_route(context.task_key)
        sanitized_prompt = self._guardrail.sanitize_input(context.prompt)
        request_hash = hashlib.sha256(sanitized_prompt.encode("utf-8")).hexdigest()
        
        start = time.perf_counter()
        full_text_collector = []
        
        def _internal_delta_handler(delta: str) -> None:
            full_text_collector.append(delta)
            if on_text_delta:
                on_text_delta(delta)


        if route.provider == "openai":
            async for chunk in self._yield_openai_stream_async(
                route=route,
                prompt=sanitized_prompt,
                system_prompt=context.system_prompt,
                on_text_delta=_internal_delta_handler
            ):
                yield chunk
        elif route.provider == "mock":
            # Simulate streaming (async)
            mock_res = self._invoke_mock(task_key=context.task_key, prompt=sanitized_prompt)
            text = self._normalize_text_payload(task_key=context.task_key, raw_payload=mock_res)
            chunk_size = 4
            for i in range(0, len(text), chunk_size):
                chunk = text[i:i+chunk_size]
                _internal_delta_handler(chunk)
                yield chunk
                await asyncio.sleep(0.02)
        else:
            raise RuntimeError(f"Async mode not supported for provider '{route.provider}' yet")

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
                confidence=0.9,
                risk_tags=[],
                policy_flags=[],
                input_summary=sanitized_prompt[:200],
                output_summary=full_text[:500],
                provider=route.provider,
                model_name=route.model_name,
                prompt_version=route.prompt_version,
            )

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
        """Core invocation flow."""
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
                    system_prompt=context.system_prompt,
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
        system_prompt: str = "",
        on_text_delta: Callable[[str], None] | None = None,
        mode: str = "json",
    ) -> Any:
        """Invoke concrete provider."""
        if route.provider == "mock":
            return self._invoke_mock(task_key=task_key, prompt=prompt)
        if route.provider == "openai":
            return self._invoke_openai(
                route=route,
                prompt=prompt,
                system_prompt=system_prompt,
                on_text_delta=on_text_delta,
                mode=mode,
            )
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
        """Validate payload by task contract."""
        if task_key == "resume_parse":
            return ResumeParseLLMOutput.model_validate(payload).model_dump()
        if task_key == "candidate_score":
            return CandidateScoreLLMOutput.model_validate(payload).model_dump()
        if task_key == "candidate_evaluation":
            sanitized = self._sanitize_candidate_evaluation_payload(payload)
            return CandidateEvaluationLLMOutput.model_validate(sanitized).model_dump()
        if task_key == "intent_classify":
            return IntentClassifyLLMOutput.model_validate(payload).model_dump()
        if task_key == "reply_generate":
            return ReplyGenerateLLMOutput.model_validate(payload).model_dump()
        if task_key == "interview_question_set":
            return InterviewQuestionSetLLMOutput.model_validate(payload).model_dump()
        if task_key == "interview_followup":
            return InterviewFollowupLLMOutput.model_validate(payload).model_dump()
        return payload

    def _sanitize_candidate_evaluation_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Best-effort normalization for candidate evaluation payload."""
        data = dict(payload or {})

        def _num(value: Any, default: float = 0.0) -> float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        def _list_str(value: Any) -> list[str]:
            if isinstance(value, list):
                return [str(item).strip() for item in value if str(item).strip()]
            if isinstance(value, str) and value.strip():
                return [value.strip()]
            return []

        def _dict_float(value: Any) -> dict[str, float]:
            if not isinstance(value, dict):
                return {}
            normalized: dict[str, float] = {}
            for k, v in value.items():
                key = str(k).strip()
                if not key:
                    continue
                try:
                    normalized[key] = float(v)
                except (TypeError, ValueError):
                    continue
            return normalized

        def _dict_str(value: Any) -> dict[str, str]:
            if not isinstance(value, dict):
                return {}
            normalized: dict[str, str] = {}
            for k, v in value.items():
                key = str(k).strip()
                if not key:
                    continue
                text = str(v).strip()
                if not text:
                    continue
                normalized[key] = text
            return normalized

        data["match_score"] = _num(data.get("match_score"))
        data["competitiveness_score"] = _num(data.get("competitiveness_score"))
        data["final_score"] = _num(data.get("final_score"))

        confidence = _num(data.get("confidence_score"))
        # If model returned a percent-like value (e.g. 82), normalize to 0-1.
        if confidence > 1.0:
            confidence = confidence / 100.0
        data["confidence_score"] = max(0.0, min(confidence, 1.0))

        data["dimension_scores"] = _dict_float(data.get("dimension_scores"))
        data["job_requirement_coverage"] = _dict_str(data.get("job_requirement_coverage"))

        data["strengths"] = _list_str(data.get("strengths"))
        data["weaknesses"] = _list_str(data.get("weaknesses"))
        data["highlights"] = _list_str(data.get("highlights"))
        data["risk_flags"] = _list_str(data.get("risk_flags"))
        data["summary"] = str(data.get("summary") or "").strip()

        recommendation = str(data.get("recommendation") or "").strip().lower()
        if recommendation not in {"strong_recommend", "recommend", "review", "reject"}:
            recommendation = "review"
        data["recommendation"] = recommendation
        return data

    def _invoke_mock(self, *, task_key: str, prompt: str) -> dict[str, Any]:
        """Mock provider for offline deterministic outputs."""
        lower = prompt.lower()
        if task_key == "resume_parse":
            skills = []
            for token in ("python", "fastapi", "mysql", "java", "golang", "kubernetes"):
                if token in lower:
                    skills.append(token)
            years_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:骞磡years?)", prompt, re.IGNORECASE)
            years = float(years_match.group(1)) if years_match else None
            education = None
            if "鏈" in prompt or "bachelor" in lower:
                education = "鏈"
            elif "纭曞＋" in prompt or "master" in lower:
                education = "纭曞＋"
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
        if task_key == "candidate_evaluation":
            skill_hits = sum(1 for token in ("python", "java", "golang", "fastapi", "spring", "mysql", "redis", "docker", "kubernetes") if token in lower)
            education_hits = sum(1 for token in ("博士", "phd", "硕士", "master", "本科", "bachelor") if token in lower)
            work_hits = sum(1 for token in ("负责", "owner", "lead", "上线", "deliver", "performance", "优化", "架构") if token in lower)
            project_hits = sum(1 for token in ("项目", "project", "重构", "系统", "平台", "服务") if token in lower)
            contest_hits = sum(1 for token in ("竞赛", "比赛", "获奖", "award", "acm", "hackathon") if token in lower)
            academic_hits = sum(1 for token in ("gpa", "绩点", "成绩", "排名", "奖学金") if token in lower)
            risk_hits = sum(1 for token in ("风险", "gap", "缺失", "空窗", "短期", "低匹配") if token in lower)

            evidence_signal = skill_hits + work_hits + project_hits + contest_hits + academic_hits
            education_score = min(100.0, 40.0 + education_hits * 18.0)
            work_experience_score = min(100.0, 35.0 + work_hits * 11.0 + skill_hits * 3.0)
            project_experience_score = min(100.0, 35.0 + project_hits * 11.0 + work_hits * 4.0)
            contest_score = min(100.0, 30.0 + contest_hits * 15.0)
            academic_score = min(100.0, 30.0 + academic_hits * 14.0 + education_hits * 4.0)
            skill_match = min(100.0, 32.0 + skill_hits * 7.0)
            evidence_quality = max(20.0, min(100.0, 28.0 + evidence_signal * 4.5 - risk_hits * 6.0))

            match_score = round(
                education_score * 0.14
                + work_experience_score * 0.22
                + project_experience_score * 0.22
                + contest_score * 0.08
                + academic_score * 0.10
                + skill_match * 0.24,
                2,
            )
            competitiveness_score = round(
                work_experience_score * 0.25
                + project_experience_score * 0.27
                + contest_score * 0.10
                + academic_score * 0.10
                + evidence_quality * 0.28,
                2,
            )
            final_score = round(
                max(0.0, min(100.0, match_score * 0.60 + competitiveness_score * 0.40 - risk_hits * 2.0)),
                2,
            )
            recommendation = (
                "strong_recommend"
                if final_score >= 88
                else "recommend"
                if final_score >= 75
                else "review"
                if final_score >= 60
                else "reject"
            )
            confidence = round(max(0.35, min(0.95, 0.38 + evidence_signal * 0.03 - risk_hits * 0.03)), 2)
            weaknesses: list[str] = []
            if work_experience_score < 65:
                weaknesses.append("工作经验与岗位要求匹配度不足")
            if project_experience_score < 65:
                weaknesses.append("项目经历深度或结果证据不足")
            if contest_score < 55:
                weaknesses.append("竞赛或奖项证据较弱")
            if academic_score < 60:
                weaknesses.append("成绩/GPA 证据不充分")
            if evidence_quality < 60:
                weaknesses.append("简历证据完整性不足")
            risk_flags = []
            if evidence_quality < 58:
                risk_flags.append("evidence_quality_low")
            if skill_match < 60:
                risk_flags.append("skill_match_low")
            if risk_hits > 0:
                risk_flags.append("resume_risk_signal")
            return {
                "match_score": match_score,
                "competitiveness_score": competitiveness_score,
                "final_score": final_score,
                "confidence_score": confidence,
                "dimension_scores": {
                    "education_score": round(education_score, 2),
                    "work_experience_score": round(work_experience_score, 2),
                    "project_experience_score": round(project_experience_score, 2),
                    "contest_score": round(contest_score, 2),
                    "academic_score": round(academic_score, 2),
                    "skill_match": round(skill_match, 2),
                    "evidence_quality": round(evidence_quality, 2),
                },
                "strengths": [
                    "核心技能和岗位要求存在较高重合",
                    "简历中有可识别的项目与交付证据",
                ],
                "weaknesses": weaknesses,
                "highlights": [
                    f"学历/工作/项目/竞赛/成绩综合评分为 {final_score}",
                    f"证据充分性评分为 {evidence_quality}",
                ],
                "risk_flags": risk_flags,
                "recommendation": recommendation,
                "summary": "模拟评估：已按学历、工作经验、项目经验、竞赛与成绩等多维度完成评分，分数已做拉开用于筛选。",
                "job_requirement_coverage": {
                    "education": "matched" if education_score >= 75 else "partial",
                    "work_experience": "matched" if work_experience_score >= 75 else "partial",
                    "project_experience": "matched" if project_experience_score >= 75 else "partial",
                    "contest": "matched" if contest_score >= 65 else "partial",
                    "academic": "matched" if academic_score >= 70 else "partial",
                },
            }
        if task_key == "intent_classify":
            if any(keyword in lower for keyword in ("salary", "package", "薪资", "薪酬")):
                return {"intent": "salary", "confidence": 0.58, "policy_flags": ["need_human_review"]}
            if any(keyword in lower for keyword in ("你好", "hello", "hi")):
                return {"intent": "greeting", "confidence": 0.94, "policy_flags": []}
            return {"intent": "general", "confidence": 0.75, "policy_flags": []}
        if task_key == "reply_generate":
            samples = [
                "收到你的消息，我们会尽快确认后续安排。",
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
        system_prompt: str = "",
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
        responses_supported = False
        should_stream = self._settings.llm_streaming_enabled and on_text_delta is not None
        if should_stream:
            try:
                return self._invoke_openai_stream(
                    route=route,
                    prompt=prompt,
                    system_prompt=system_prompt,
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
        system_prompt: str = "",
        mode: str = "json",
    ) -> Any:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        chat_body = {
            "model": route.model_name,
            "messages": messages,
            "temperature": round(route.temperature_milli / 1000, 3),
        }
        if mode == "json" and ("gpt-" in route.model_name or "o1-" in route.model_name):
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

    async def _yield_openai_stream_async(
        self,
        *,
        route: ModelRoute,
        prompt: str,
        system_prompt: str = "",
        on_text_delta: Callable[[str], None] | None = None,
    ) -> AsyncIterator[str]:
        """Internal async generator for OpenAI stream."""
        import os
        api_key = (self._settings.llm_api_key or os.getenv("AI_HR_LLM_API_KEY") or "").strip()
        base_url = (self._settings.llm_base_url or os.getenv("AI_HR_LLM_BASE_URL") or "https://api.openai.com").strip().rstrip("/")
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        chat_body = {
            "model": route.model_name,
            "messages": messages,
            "temperature": round(route.temperature_milli / 1000, 3),
            "stream": True,
        }
        
        for attempt in range(2):
            try:
                url = f"{base_url}/v1/chat/completions"
                async with self._async_session.stream("POST", url, json=chat_body, headers=headers, timeout=max(1, route.timeout_seconds)) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        line = line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        body = line[5:].strip()
                        if body == "[DONE]":
                            break
                        try:
                            payload = json.loads(body)
                            delta_text = self._extract_stream_delta_text(payload)
                            if delta_text:
                                if on_text_delta:
                                    on_text_delta(delta_text)
                                yield delta_text
                        except Exception:
                            continue
                return 
            except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError) as exc:
                if attempt == 0:
                    logger.warning(f"LLM Async Stream connection error, retrying: {exc}")
                    continue
                logger.error(f"LLM Async Stream Yield Error after retry: {exc}", exc_info=True)
                raise
            except Exception as exc:
                logger.error(f"LLM Async Stream Yield Error: {exc}", exc_info=True)
                raise


    def _invoke_openai_stream(
        self,
        *,
        route: ModelRoute,
        prompt: str,
        base_url: str,
        headers: dict[str, str],
        system_prompt: str = "",
        on_text_delta: Callable[[str], None] | None = None,
        mode: str = "json",
    ) -> Any:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        chat_body = {
            "model": route.model_name,
            "messages": messages,
            "temperature": round(route.temperature_milli / 1000, 3),
            "stream": True,
        }
        if mode == "json":
            chat_body["response_format"] = {"type": "json_object"}
            
        text_parts: list[str] = []
        try:
            # Using httpx.Client (self._session) for connection pooling/keep-alive
            url = f"{base_url}/v1/chat/completions"
            with self._session.stream("POST", url, json=chat_body, headers=headers, timeout=max(1, route.timeout_seconds)) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    line = line.strip()
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
            logger.error(f"LLM Stream Error (httpx): {exc}", exc_info=True)
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
