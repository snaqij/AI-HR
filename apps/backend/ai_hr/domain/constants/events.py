from __future__ import annotations

from enum import StrEnum


class InterviewEventType(StrEnum):
    AGENT_STATE = "agent.state"
    CANDIDATE_FINAL = "candidate.final"
    QUESTION_UPDATE = "question.update"
    QUESTION_FINAL = "question.final"
    TTS_PACKET = "tts.packet"
    LLM_SENTENCE = "llm.sentence"
    REPORT_GENERATED = "ai_interview.report.generated"
