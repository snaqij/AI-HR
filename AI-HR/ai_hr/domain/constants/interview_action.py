from __future__ import annotations

from enum import StrEnum


class InterviewAction(StrEnum):
    AUTO_CONTINUE = "auto_continue"
    HANDOFF = "handoff"
    BLOCKED = "blocked"
