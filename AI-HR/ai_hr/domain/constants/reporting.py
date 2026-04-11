from __future__ import annotations

from enum import StrEnum


class InterviewRecommendation(StrEnum):
    ADVANCE = "advance"
    MANUAL_REVIEW = "manual_review"


class CandidateStageResult(StrEnum):
    INTERVIEW_DONE = "interview_done"


class InterviewOutcomeStatus(StrEnum):
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class RuntimeMode(StrEnum):
    RULE_ONLY = "rule_only"
