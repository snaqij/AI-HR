from __future__ import annotations

from enum import StrEnum


class PromptTaskKey(StrEnum):
    RESUME_PARSE = "resume_parse"
    CANDIDATE_SCORE = "candidate_score"
    CANDIDATE_EVALUATION = "candidate_evaluation"
    ANSWER_EVALUATION = "answer_evaluation"
    INTENT_CLASSIFY = "intent_classify"
    REPLY_GENERATE = "reply_generate"
    INTERVIEW_QUESTION_SET = "interview_question_set"
    INTERVIEW_FOLLOWUP = "interview_followup"
    CONTACT_EXTRACT = "contact_extract"


DEFAULT_INTERVIEW_QUESTION_SET_PROMPT_VERSION = "v2"
DEFAULT_INTERVIEW_FOLLOWUP_PROMPT_VERSION = "v5"
