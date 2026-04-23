from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .config_loader import RoleConfigLoader

logger = logging.getLogger(__name__)


@dataclass
class RoleMatch:
    """Candidate role match scored from job signals."""

    role_id: str
    score: float
    config: Dict
    match_details: Dict


@dataclass
class RoleProfileResult:
    """Structured role resolution result."""

    config: Dict
    role_id: str
    source: str
    score: float
    match_details: Dict


class RoleProfiler:
    """Resolve the most appropriate role configuration for a job."""

    def __init__(self, config_loader: RoleConfigLoader | None = None):
        self.config_loader = config_loader or RoleConfigLoader()
        self._all_configs_cache: Optional[Dict[str, Dict]] = None
        logger.info("role.profiler.initialized")

    def identify_role(
        self,
        job_title: str | None = None,
        jd: str | None = None,
        skills: List[str] | None = None,
        explicit_role_id: str | None = None,
    ) -> Dict:
        return self.identify_role_profile(
            job_title=job_title,
            jd=jd,
            skills=skills,
            explicit_role_id=explicit_role_id,
        ).config

    def identify_role_profile(
        self,
        job_title: str | None = None,
        jd: str | None = None,
        skills: List[str] | None = None,
        explicit_role_id: str | None = None,
    ) -> RoleProfileResult:
        if explicit_role_id:
            config = self.config_loader.load_config(explicit_role_id)
            if config:
                logger.info(
                    "role.identify.explicit",
                    extra={"role_id": explicit_role_id, "job_title": job_title},
                )
                resolved_role_id = str(config.get("role", {}).get("id") or explicit_role_id)
                return RoleProfileResult(
                    config=config,
                    role_id=resolved_role_id,
                    source="explicit",
                    score=1.0,
                    match_details={"explicit_role_id": explicit_role_id},
                )
            logger.warning(
                "role.identify.explicit_not_found",
                extra={"role_id": explicit_role_id, "job_title": job_title},
            )

        match = self._find_best_match(job_title, jd, skills)
        if match and match.score > 0:
            logger.info(
                "role.identify.matched",
                extra={
                    "role_id": match.role_id,
                    "score": match.score,
                    "job_title": job_title,
                    "match_details": match.match_details,
                },
            )
            return RoleProfileResult(
                config=match.config,
                role_id=match.role_id,
                source="auto_match",
                score=float(match.score),
                match_details=dict(match.match_details or {}),
            )

        logger.info(
            "role.identify.fallback_to_base",
            extra={"job_title": job_title, "reason": "no_match_found"},
        )
        base_config = self.config_loader.load_base_config()
        return RoleProfileResult(
            config=base_config,
            role_id=str(base_config.get("role", {}).get("id") or "_base"),
            source="fallback_base",
            score=0.0,
            match_details={"reason": "no_match_found"},
        )

    def _find_best_match(
        self,
        job_title: str | None = None,
        jd: str | None = None,
        skills: List[str] | None = None,
    ) -> Optional[RoleMatch]:
        all_configs = self._get_all_configs()
        text = " ".join(filter(None, [job_title or "", jd or ""]))
        skills = skills or []

        if not text and not skills:
            return None

        matches = []
        for role_id, config in all_configs.items():
            if role_id.startswith("_"):
                continue

            match_rules = config.get("role", {}).get("match_rules", {})
            if not match_rules:
                continue

            score, details = self._calculate_match_score(text, skills, match_rules)
            if score > 0:
                matches.append(
                    RoleMatch(
                        role_id=role_id,
                        score=score,
                        config=config,
                        match_details=details,
                    )
                )

        if matches:
            return max(matches, key=lambda m: m.score)
        return None

    def _calculate_match_score(
        self,
        text: str,
        skills: List[str],
        match_rules: Dict,
    ) -> Tuple[float, Dict]:
        text_lower = text.lower()
        skills_lower = [s.lower() for s in skills]

        keywords = match_rules.get("keywords", [])
        keyword_matches = [kw for kw in keywords if kw.lower() in text_lower]
        keyword_score = len(keyword_matches) * 2.0

        required_skills = match_rules.get("skills", [])
        skill_matches = [
            skill
            for skill in required_skills
            if skill.lower() in skills_lower or skill.lower() in text_lower
        ]
        skill_score = len(skill_matches) * 1.0

        total_score = keyword_score + skill_score
        details = {
            "keyword_matches": keyword_matches,
            "skill_matches": skill_matches,
            "keyword_score": keyword_score,
            "skill_score": skill_score,
        }

        logger.debug(
            "role.match.score_calculated",
            extra={"total_score": total_score, "details": details},
        )
        return total_score, details

    def _get_all_configs(self) -> Dict[str, Dict]:
        if self._all_configs_cache is None:
            self._all_configs_cache = self.config_loader.load_all_configs()
        return self._all_configs_cache

    def clear_cache(self) -> None:
        self._all_configs_cache = None
        logger.info("role.profiler.cache_cleared")
