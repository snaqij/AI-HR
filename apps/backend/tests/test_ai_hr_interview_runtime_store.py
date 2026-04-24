from __future__ import annotations

import time

from ai_hr.core.config import get_settings
from ai_hr.services.interview_runtime.factory import get_interview_runtime_store
from ai_hr.services.interview_runtime.memory_store import MemoryInterviewRuntimeStore


def test_reserve_event_should_deduplicate_with_ttl() -> None:
    store = MemoryInterviewRuntimeStore()
    assert store.reserve_event(session_id="s1", event_id="e1", ttl_seconds=1) is True
    assert store.reserve_event(session_id="s1", event_id="e1", ttl_seconds=1) is False
    time.sleep(1.1)
    assert store.reserve_event(session_id="s1", event_id="e1", ttl_seconds=1) is True


def test_question_pack_save_and_get() -> None:
    store = MemoryInterviewRuntimeStore()
    question_pack = {"questions": [{"id": "q1", "question": "Q1"}], "version": 1}
    store.save_question_pack(session_id="s1", version=1, question_pack=question_pack, ttl_seconds=30)
    latest = store.get_question_pack(session_id="s1")
    assert latest is not None
    assert latest["version"] == 1
    specific = store.get_question_pack(session_id="s1", version=1)
    assert specific is not None
    assert specific["questions"][0]["id"] == "q1"


def test_session_state_patch_should_merge() -> None:
    store = MemoryInterviewRuntimeStore()
    store.init_session_state(
        session_id="s1",
        state={"stage": "intro", "asked": 0},
        ttl_seconds=30,
    )
    merged = store.patch_session_state(
        session_id="s1",
        patch={"asked": 1, "active_question_id": "q1"},
        ttl_seconds=30,
    )
    assert merged["stage"] == "intro"
    assert merged["asked"] == 1
    assert merged["active_question_id"] == "q1"


def test_followup_cache_set_get() -> None:
    store = MemoryInterviewRuntimeStore()
    assert store.get_followup_cache(key="k1") is None
    store.set_followup_cache(key="k1", value="请补充指标", ttl_seconds=30)
    assert store.get_followup_cache(key="k1") == "请补充指标"


def test_runtime_should_fallback_when_redis_temporarily_unavailable(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("AI_HR_AI_INTERVIEW_REDIS_ENABLED", "true")
    monkeypatch.setenv("AI_HR_REDIS_URL", "redis://127.0.0.1:6399/15")
    get_settings.cache_clear()
    get_interview_runtime_store.cache_clear()
    store = get_interview_runtime_store()
    assert isinstance(store, MemoryInterviewRuntimeStore)
    get_interview_runtime_store.cache_clear()
    get_settings.cache_clear()
