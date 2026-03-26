"""AI 简历解析与标准化服务。"""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.exceptions import InvalidStateError, ResourceNotFoundError
from ..repositories.ai_observability import AIObservabilityRepository
from ..repositories.ai_runtime import AIRuntimeRepository
from ..repositories.candidates import CandidateRepository
from ..repositories.resume_profiles import ResumeProfileRepository
from ..schemas.ai_resume import (
    CandidateResumeProfileResult,
    ResumeNormalizeRequest,
    ResumeNormalizeResult,
    ResumeParseRequest,
    ResumeParseResult,
    ResumeProfilePayload,
    ResumeRiskItem,
)
from .llm.client import InvokeContext, LLMClient
from .llm.guardrails import GuardrailService
from .llm.prompts import get_prompt_template
from .llm.router import ModelRouter

PARSER_VERSION_HEURISTIC = "heuristic-v1"
PARSER_VERSION_LLM = "llm-v1"

_SKILL_KEYWORDS = [
    "python",
    "fastapi",
    "mysql",
    "sqlalchemy",
    "java",
    "golang",
    "kubernetes",
    "docker",
    "linux",
]

_EDUCATION_LEVELS = ["博士", "硕士", "本科", "大专", "中专", "高中"]


class AIResumeService:
    """负责简历解析、标准化与结构化画像查询。"""

    def __init__(self, session: Session):
        """注入数据库会话并初始化依赖。"""
        self._session = session
        self._settings = get_settings()
        self._candidate_repository = CandidateRepository(session)
        self._resume_repository = ResumeProfileRepository(session)

        runtime_repository = AIRuntimeRepository(session)
        self._runtime_repository = runtime_repository
        observability_repository = AIObservabilityRepository(session)
        self._llm_client = LLMClient(
            router=ModelRouter(runtime_repository),
            guardrail_service=GuardrailService(),
            observability_repository=observability_repository,
        )

    def parse_resume(self, payload: ResumeParseRequest) -> ResumeParseResult:
        """执行简历解析并写入结构化画像。"""
        candidate = self._candidate_repository.get(payload.candidate_id)
        raw_text = (payload.resume_text or candidate.resume_text or "").strip()
        if not raw_text:
            raise InvalidStateError(f"Candidate '{payload.candidate_id}' has no resume text to parse")

        parser_version = PARSER_VERSION_HEURISTIC
        parsed, llm_risk_tags = self._parse_with_heuristic(raw_text=raw_text, raw_profile=candidate.raw_profile or {})
        if self._is_llm_enabled():
            llm_parsed, llm_risk_tags = self._parse_with_llm(
                candidate_id=candidate.id,
                raw_text=raw_text,
                raw_profile=candidate.raw_profile or {},
            )
            if llm_parsed:
                parsed = llm_parsed
                parser_version = PARSER_VERSION_LLM

        normalized = self._normalize_profile(parsed)
        confidence = self._estimate_confidence(parsed, raw_text)
        risks = self._detect_risks(normalized, raw_text, extra_risk_tags=llm_risk_tags)

        profile_entity = self._resume_repository.upsert_profile(
            candidate_id=candidate.id,
            raw_text=raw_text,
            parsed_json=parsed,
            normalized_json=normalized,
            parse_status="parsed",
            parser_version=parser_version,
            confidence=confidence,
        )
        risk_entities = self._resume_repository.replace_risks(candidate_id=candidate.id, risks=risks)
        self._session.commit()
        self._session.refresh(profile_entity)
        for risk in risk_entities:
            self._session.refresh(risk)
        return ResumeParseResult(profile=self._to_profile_payload(profile_entity, risk_entities))

    def normalize_resume(self, payload: ResumeNormalizeRequest) -> ResumeNormalizeResult:
        """对已有解析结果执行标准化刷新。"""
        candidate = self._candidate_repository.get(payload.candidate_id)
        profile = self._resume_repository.get_profile(candidate.id)
        raw_text = (candidate.resume_text or "").strip()
        if profile is None:
            if not raw_text:
                raise InvalidStateError(f"Candidate '{payload.candidate_id}' has no resume text to normalize")
            parsed, extra_risk_tags = self._parse_with_heuristic(raw_text=raw_text, raw_profile=candidate.raw_profile or {})
            parser_version = PARSER_VERSION_HEURISTIC
        else:
            parsed = dict(profile.parsed_json or {})
            parser_version = profile.parser_version
            extra_risk_tags = []
            if not raw_text:
                raw_text = (profile.raw_text or "").strip()

        normalized = self._normalize_profile(parsed)
        confidence = self._estimate_confidence(parsed, raw_text)
        risks = self._detect_risks(normalized, raw_text, extra_risk_tags=extra_risk_tags)

        profile_entity = self._resume_repository.upsert_profile(
            candidate_id=candidate.id,
            raw_text=raw_text,
            parsed_json=parsed,
            normalized_json=normalized,
            parse_status="normalized",
            parser_version=parser_version,
            confidence=confidence,
        )
        risk_entities = self._resume_repository.replace_risks(candidate_id=candidate.id, risks=risks)
        self._session.commit()
        self._session.refresh(profile_entity)
        for risk in risk_entities:
            self._session.refresh(risk)
        return ResumeNormalizeResult(profile=self._to_profile_payload(profile_entity, risk_entities))

    def get_candidate_resume_profile(self, candidate_id: str) -> CandidateResumeProfileResult:
        """查询候选人简历画像。"""
        self._candidate_repository.get(candidate_id)
        profile = self._resume_repository.get_profile(candidate_id)
        if profile is None:
            raise ResourceNotFoundError(f"Resume profile for candidate '{candidate_id}' was not found")
        risks = self._resume_repository.list_risks(candidate_id)
        return CandidateResumeProfileResult(profile=self._to_profile_payload(profile, risks))

    def _parse_with_llm(self, *, candidate_id: str, raw_text: str, raw_profile: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        """调用 LLM 执行简历解析，失败时返回空结果并打标。"""
        template = get_prompt_template("resume_parse", "v1")
        prompt = "\n".join([template.system_prompt, template.render(resume_text=raw_text)])
        result = self._llm_client.invoke_json(
            InvokeContext(
                task_key="resume_parse",
                trace_id=str(uuid.uuid4()),
                prompt=prompt,
                entity_type="candidate",
                entity_id=candidate_id,
            )
        )

        if result.fallback_used or result.content.get("error"):
            return None, ["llm_unavailable"]

        content = dict(result.content)
        parsed: dict[str, Any] = {}
        parsed["skills"] = [str(item).strip() for item in content.get("skills", []) if str(item).strip()]
        if content.get("experience_years") is not None:
            try:
                parsed["experience_years"] = float(content["experience_years"])
            except (TypeError, ValueError):
                pass
        if content.get("education_level"):
            parsed["education_level"] = str(content["education_level"])
        if isinstance(content.get("projects"), list):
            parsed["projects"] = content["projects"]
        if "job_hops" in raw_profile:
            try:
                parsed["job_hops"] = int(raw_profile["job_hops"])
            except (TypeError, ValueError):
                pass
        return parsed, [str(item) for item in content.get("risk_tags", [])]

    def _parse_with_heuristic(self, *, raw_text: str, raw_profile: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        """基于文本与 raw_profile 执行启发式解析。"""
        lower_text = raw_text.lower()
        parsed: dict[str, Any] = {}

        skills = set()
        for skill in raw_profile.get("skills", []):
            value = str(skill).strip()
            if value:
                skills.add(value)
        for keyword in _SKILL_KEYWORDS:
            if keyword in lower_text:
                skills.add(keyword)
        parsed["skills"] = sorted(skills, key=lambda item: item.lower())

        years = self._extract_years(raw_text)
        if years is not None:
            parsed["experience_years"] = years

        education = self._extract_education(raw_text, raw_profile)
        if education:
            parsed["education_level"] = education

        projects = raw_profile.get("projects")
        if isinstance(projects, list):
            parsed["projects"] = projects
        else:
            parsed["projects"] = self._extract_project_hints(raw_text)

        if "job_hops" in raw_profile:
            try:
                parsed["job_hops"] = int(raw_profile["job_hops"])
            except (TypeError, ValueError):
                pass
        return parsed, []

    def _normalize_profile(self, parsed: dict[str, Any]) -> dict[str, Any]:
        """对解析结果执行字段标准化。"""
        normalized: dict[str, Any] = dict(parsed)

        skills = []
        for item in parsed.get("skills", []):
            text = str(item).strip()
            if not text:
                continue
            canonical = text.lower().replace(" ", "")
            if canonical == "python3":
                canonical = "python"
            skills.append(canonical)
        normalized["skills"] = sorted(set(skills))

        if "experience_years" in parsed:
            try:
                years = float(parsed["experience_years"])
                normalized["experience_years"] = round(max(0.0, years), 1)
            except (TypeError, ValueError):
                normalized.pop("experience_years", None)

        education = str(parsed.get("education_level") or "").strip().lower()
        if education in {"phd", "doctor", "博士"}:
            normalized["education_level"] = "博士"
        elif education in {"master", "硕士", "研究生"}:
            normalized["education_level"] = "硕士"
        elif education in {"bachelor", "本科", "学士"}:
            normalized["education_level"] = "本科"
        elif education in {"college", "大专"}:
            normalized["education_level"] = "大专"
        elif education:
            normalized["education_level"] = str(parsed["education_level"])
        return normalized

    def _detect_risks(self, normalized: dict[str, Any], raw_text: str, extra_risk_tags: list[str] | None = None) -> list[dict[str, str]]:
        """识别简历风险标签。"""
        risk_map: dict[str, dict[str, str]] = {}

        def add_risk(code: str, level: str, detail: str) -> None:
            risk_map[code] = {"risk_code": code, "risk_level": level, "detail": detail}

        skills = normalized.get("skills", [])
        if not skills:
            add_risk("skills_missing", "medium", "未识别到可用技能字段，需人工复核简历。")
        years = normalized.get("experience_years")
        if years is None:
            add_risk("experience_missing", "low", "未提取到明确工作年限。")
        job_hops = normalized.get("job_hops")
        if isinstance(job_hops, int) and job_hops >= 4:
            add_risk("job_hops_high", "medium", "候选人历史跳槽频次偏高。")
        if len(raw_text) < 80:
            add_risk("resume_too_short", "low", "简历文本较短，信息完整度可能不足。")

        for tag in extra_risk_tags or []:
            if tag not in risk_map:
                add_risk(tag, "low", f"模型风险标签：{tag}")
        return list(risk_map.values())

    def _estimate_confidence(self, parsed: dict[str, Any], raw_text: str) -> float:
        """估算解析置信度。"""
        score = 0.35
        if parsed.get("skills"):
            score += 0.25
        if parsed.get("experience_years") is not None:
            score += 0.2
        if parsed.get("education_level"):
            score += 0.1
        if len(raw_text) >= 120:
            score += 0.1
        return round(min(score, 0.98), 2)

    def _extract_years(self, raw_text: str) -> float | None:
        """从简历文本中提取年限。"""
        match = re.search(r"(\d+(?:\.\d+)?)\s*(?:年|years?)", raw_text, re.IGNORECASE)
        if not match:
            return None
        try:
            return float(match.group(1))
        except ValueError:
            return None

    def _extract_education(self, raw_text: str, raw_profile: dict[str, Any]) -> str | None:
        """提取最高学历关键词。"""
        for key in ("education", "education_level"):
            value = raw_profile.get(key)
            if value:
                return str(value)
        for level in _EDUCATION_LEVELS:
            if level in raw_text:
                return level
        token = re.search(r"\b(master|bachelor|phd)\b", raw_text, re.IGNORECASE)
        if token:
            return token.group(1)
        return None

    def _extract_project_hints(self, raw_text: str) -> list[dict[str, str]]:
        """从文本中抽取简化项目提示。"""
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        project_lines = [line for line in lines if "项目" in line or "project" in line.lower()]
        return [{"name": f"project-{idx}", "summary": line[:120]} for idx, line in enumerate(project_lines[:3], start=1)]

    def _to_profile_payload(self, profile, risks) -> ResumeProfilePayload:
        """将 ORM 对象转换为 API 响应模型。"""
        return ResumeProfilePayload(
            candidate_id=profile.candidate_id,
            raw_text=profile.raw_text or "",
            parse_status=profile.parse_status,
            parser_version=profile.parser_version,
            confidence=profile.confidence,
            parsed_profile=profile.parsed_json or {},
            normalized_profile=profile.normalized_json or {},
            risks=[ResumeRiskItem(risk_code=item.risk_code, risk_level=item.risk_level, detail=item.detail) for item in risks],
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )

    def _is_llm_enabled(self) -> bool:
        """判定简历解析链路是否启用 LLM。"""
        return self._runtime_repository.is_feature_enabled(
            feature_key="ai_resume_llm",
            default_enabled=self._settings.ai_resume_llm_enabled,
        )


def get_ai_resume_service(session: Session) -> AIResumeService:
    """返回绑定当前数据库会话的 AIResumeService。"""
    return AIResumeService(session)
