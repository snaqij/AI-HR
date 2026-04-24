from __future__ import annotations

from enum import StrEnum


class InterviewSessionStatus(StrEnum):
    CREATED = "created"
    IN_PROGRESS = "in_progress"
    FAILED = "failed"
