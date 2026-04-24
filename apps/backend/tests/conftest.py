from __future__ import annotations

import os

from ai_hr.core.config import get_settings


# Keep test runs deterministic regardless of local infra/env/.env.dev values.
os.environ.setdefault("AI_HR_RTC_PROVIDER", "mock")
os.environ.setdefault("AI_HR_ASR_PROVIDER", "mock")
os.environ.setdefault("AI_HR_TTS_PROVIDER", "mock")
os.environ.setdefault("AI_HR_LLM_PROVIDER", "mock")
os.environ.setdefault("AI_HR_AI_INTERVIEW_LLM_ENABLED", "false")
get_settings.cache_clear()
