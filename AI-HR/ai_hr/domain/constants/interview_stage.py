from __future__ import annotations

from enum import StrEnum


class InterviewStage(StrEnum):
    OPENING = "S1"
    SELF_INTRO = "S2"
    TECH_STACK = "S3"
    PROJECT_DEEP_DIVE = "S4"
    JD_MATCH = "S5"
    GENERAL_PROBE = "S6"
    COMPANY_QA = "S7"
    CLOSING = "S8"


class InterviewStageGroup(StrEnum):
    INTRO = "intro"
    CORE = "core"
    DEEP_DIVE = "deep_dive"
