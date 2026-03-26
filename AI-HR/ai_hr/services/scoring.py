"""Candidate scoring service."""

from __future__ import annotations

from dataclasses import dataclass
import re

SCORE_VERSION = "ai-score-v1"


@dataclass(slots=True)
class ScoringResult:
    score_version: str
    total_score: float
    dimensions: dict[str, float]
    risk_tags: list[str]
    explanation: str


def score_candidate_profile(
    *,
    resume_text: str | None,
    profile: dict,
    job_requirements: str | None,
) -> ScoringResult:
    text = (resume_text or "").lower()
    skills = {str(skill).strip().lower() for skill in profile.get("skills", []) if str(skill).strip()}
    text_tokens = set(re.findall(r"[a-zA-Z]{2,}", text))

    job_tokens = set(re.findall(r"[a-zA-Z]{2,}", (job_requirements or "").lower()))
    if not job_tokens:
        job_tokens = {"python", "communication", "collaboration"}

    skill_matches = len((skills | text_tokens) & job_tokens)
    skills_score = min(100.0, 40.0 + skill_matches * 12.0)

    experience_hints = sum(1 for token in {"python", "fastapi", "mysql", "sqlalchemy", "kubernetes", "golang"} if token in text_tokens or token in skills)
    experience_score = min(100.0, 35.0 + experience_hints * 10.0)

    stability_score = 70.0
    if profile.get("job_hops") is not None:
        try:
            job_hops = int(profile["job_hops"])
            stability_score = max(35.0, 85.0 - job_hops * 8.0)
        except (TypeError, ValueError):
            stability_score = 70.0

    total_score = round(skills_score * 0.5 + experience_score * 0.3 + stability_score * 0.2, 2)
    dimensions = {
        "skills_match": round(skills_score, 2),
        "experience_relevance": round(experience_score, 2),
        "stability": round(stability_score, 2),
    }
    risk_tags = _detect_scoring_risks(
        profile=profile,
        resume_text=resume_text,
        dimensions=dimensions,
    )
    explanation = (
        "skills_match reflects overlap between resume/profile skills and job requirements; "
        "experience_relevance reflects relevant technical signals in resume; "
        "stability reflects profile continuity indicators."
    )
    return ScoringResult(
        score_version=SCORE_VERSION,
        total_score=total_score,
        dimensions=dimensions,
        risk_tags=risk_tags,
        explanation=explanation,
    )


def _detect_scoring_risks(
    *,
    profile: dict,
    resume_text: str | None,
    dimensions: dict[str, float],
) -> list[str]:
    """识别评分阶段的风险标签。"""
    risks: list[str] = []
    if not (profile or {}).get("skills"):
        risks.append("skills_missing")
    if not resume_text or len(resume_text.strip()) < 80:
        risks.append("resume_too_short")
    if dimensions.get("stability", 100.0) < 50:
        risks.append("job_hops_high")
    if dimensions.get("skills_match", 100.0) < 55:
        risks.append("skills_match_low")
    return risks
