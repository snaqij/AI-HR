from __future__ import annotations

from enum import StrEnum


class SpeakerRole(StrEnum):
    CANDIDATE = "candidate"
    CANDIDATE_PARTIAL = "candidate_partial"
    AI = "ai"
