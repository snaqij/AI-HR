"""LLM 失败场景下的兜底逻辑。"""

from __future__ import annotations

from ai_hr.domain.constants import RiskTag

from ..scoring import score_candidate_profile


def fallback_resume_parse(resume_text: str) -> dict:
    """简历解析兜底输出。"""
    return {
        "skills": [],
        "experience_years": None,
        "education_level": None,
        "projects": [],
        "confidence": 0.35,
        "risk_tags": [RiskTag.LLM_UNAVAILABLE],
        "raw_text": resume_text,
    }


def fallback_candidate_score(*, resume_text: str | None, profile: dict, job_requirements: str | None) -> dict:
    """评分兜底：复用现有规则引擎。"""
    result = score_candidate_profile(
        resume_text=resume_text,
        profile=profile,
        job_requirements=job_requirements,
    )
    return {
        "total_score": result.total_score,
        "dimension_scores": result.dimensions,
        "explanation": result.explanation,
        "risk_tags": result.risk_tags + [RiskTag.LLM_UNAVAILABLE],
    }
