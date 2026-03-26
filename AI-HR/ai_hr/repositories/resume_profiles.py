"""简历画像仓储实现。"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..db.models import CandidateResumeProfile, CandidateResumeRisk


class ResumeProfileRepository:
    """封装简历解析结果与风险标签的持久化读写。"""

    def __init__(self, session: Session):
        """使用当前数据库会话初始化仓储。"""
        self._session = session

    def get_profile(self, candidate_id: str) -> CandidateResumeProfile | None:
        """按候选人 ID 获取简历画像。"""
        stmt = select(CandidateResumeProfile).where(CandidateResumeProfile.candidate_id == candidate_id)
        return self._session.execute(stmt).scalar_one_or_none()

    def list_risks(self, candidate_id: str) -> list[CandidateResumeRisk]:
        """按候选人 ID 列出风险标签。"""
        stmt = select(CandidateResumeRisk).where(CandidateResumeRisk.candidate_id == candidate_id)
        return list(self._session.execute(stmt).scalars().all())

    def upsert_profile(
        self,
        *,
        candidate_id: str,
        raw_text: str,
        parsed_json: dict,
        normalized_json: dict,
        parse_status: str,
        parser_version: str,
        confidence: float,
    ) -> CandidateResumeProfile:
        """新增或更新简历画像。"""
        profile = self.get_profile(candidate_id)
        if profile is None:
            profile = CandidateResumeProfile(
                candidate_id=candidate_id,
                raw_text=raw_text,
                parsed_json=parsed_json,
                normalized_json=normalized_json,
                parse_status=parse_status,
                parser_version=parser_version,
                confidence=confidence,
            )
            self._session.add(profile)
        else:
            profile.raw_text = raw_text
            profile.parsed_json = parsed_json
            profile.normalized_json = normalized_json
            profile.parse_status = parse_status
            profile.parser_version = parser_version
            profile.confidence = confidence
        self._session.flush()
        return profile

    def replace_risks(self, *, candidate_id: str, risks: list[dict[str, str]]) -> list[CandidateResumeRisk]:
        """替换候选人的风险标签集合。"""
        self._session.execute(delete(CandidateResumeRisk).where(CandidateResumeRisk.candidate_id == candidate_id))
        entities: list[CandidateResumeRisk] = []
        for item in risks:
            entity = CandidateResumeRisk(
                candidate_id=candidate_id,
                risk_code=item["risk_code"],
                risk_level=item["risk_level"],
                detail=item["detail"],
            )
            self._session.add(entity)
            entities.append(entity)
        self._session.flush()
        return entities

