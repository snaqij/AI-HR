"""Candidate-first arbitration for realtime interview conversations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ConversationArbiter:
    """Manage who is allowed to speak in the realtime interview loop."""

    current_turn_id: int = 0
    active_generation_id: str | None = None
    active_playback_id: str | None = None
    is_candidate_speaking: bool = False
    candidate_speaking_since_ms: int = 0
    last_speech_activity_ms: int = 0
    last_user_resume_ms: int = 0
    last_user_end_ms: int = 0
    commit_guard_until_ms: int = 0

    def on_candidate_speaking(self, *, now_ms: int, commit_guard_ms: int) -> None:
        if not self.is_candidate_speaking:
            self.candidate_speaking_since_ms = now_ms
        self.is_candidate_speaking = True
        self.last_speech_activity_ms = now_ms
        self.last_user_resume_ms = now_ms
        self.commit_guard_until_ms = max(self.commit_guard_until_ms, now_ms + max(0, commit_guard_ms))

    def on_candidate_pause(self, *, now_ms: int, commit_guard_ms: int) -> None:
        self.is_candidate_speaking = False
        self.last_user_end_ms = now_ms
        self.commit_guard_until_ms = max(self.commit_guard_until_ms, now_ms + max(0, commit_guard_ms))

    def begin_turn(self) -> int:
        self.current_turn_id += 1
        return self.current_turn_id

    def begin_generation(self, *, turn_id: int) -> str:
        generation_id = f"turn-{turn_id}-gen-{turn_id}-{self.last_speech_activity_ms}"
        self.active_generation_id = generation_id
        return generation_id

    def invalidate_generation(self) -> None:
        self.active_generation_id = None
        self.active_playback_id = None

    def is_generation_active(self, generation_id: str | None) -> bool:
        return bool(generation_id) and generation_id == self.active_generation_id

    def can_commit_tts(self, *, generation_id: str | None, now_ms: int) -> bool:
        if not self.is_generation_active(generation_id):
            return False
        if self.is_candidate_speaking:
            return False
        if now_ms < self.commit_guard_until_ms:
            return False
        return True

    def register_playback(self, *, generation_id: str, playback_id: str) -> bool:
        if not self.is_generation_active(generation_id):
            return False
        self.active_playback_id = playback_id
        return True

    def clear_playback(self, playback_id: str | None = None) -> None:
        if playback_id is None or playback_id == self.active_playback_id:
            self.active_playback_id = None
