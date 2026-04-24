from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

Role = Literal["assistant", "user"]


@dataclass(slots=True)
class DialogueTurn:
    turn_id: str
    role: Role
    text: str
    stage: str = ""
    question_id: str = ""
    trace_id: str = ""
    created_at_ms: int = 0
    topic_name: str = ""


@dataclass(slots=True)
class PendingTurn:
    question_text: str = ""
    answer_parts: list[str] = field(default_factory=list)
    stage: str = ""
    question_id: str = ""
    trace_id: str = ""
    started_at_ms: int = 0
    topic_name: str = ""


@dataclass(slots=True)
class SessionContext:
    session_id: str
    recent_turns: list[DialogueTurn] = field(default_factory=list)
    pending_turn: PendingTurn = field(default_factory=PendingTurn)
    max_turns: int = 8
    version: int = 0
    max_turn_text_chars: int = 220
    focus_experience: str = ""
    focus_module: str = ""
    active_topic_name: str = ""
    active_topic_rounds: int = 0
    known_entities: list[str] = field(default_factory=list)
    entity_aliases: dict[str, list[str]] = field(default_factory=dict)

    def append_turn(
        self,
        *,
        turn_id: str,
        role: Role,
        text: str,
        now_ms: int,
        stage: str = "",
        trace_id: str = "",
        question_id: str = "",
        topic_name: str = "",
    ) -> bool:
        normalized = self._normalize_text(text)
        if not normalized:
            return False

        if self.recent_turns:
            last = self.recent_turns[-1]
            if (
                last.role == role
                and last.text == normalized
                and last.stage == str(stage or "")
                and last.question_id == str(question_id or "")
                and last.topic_name == str(topic_name or "")
            ):
                return False

        self.recent_turns.append(
            DialogueTurn(
                turn_id=turn_id,
                role=role,
                text=normalized,
                stage=str(stage or ""),
                question_id=str(question_id or ""),
                trace_id=str(trace_id or ""),
                created_at_ms=int(now_ms or 0),
                topic_name=str(topic_name or ""),
            )
        )
        self.trim_recent_turns()
        self.version += 1
        return True

    def start_pending_question(
        self,
        *,
        turn_id: str,
        question_text: str,
        now_ms: int,
        stage: str = "",
        trace_id: str = "",
        question_id: str = "",
        topic_name: str = "",
    ) -> bool:
        normalized = self._normalize_text(question_text)
        if not normalized:
            return False

        self.pending_turn = PendingTurn(
            question_text=normalized,
            stage=str(stage or ""),
            question_id=str(question_id or ""),
            trace_id=str(trace_id or ""),
            started_at_ms=int(now_ms or 0),
            topic_name=str(topic_name or ""),
        )
        return self.append_turn(
            turn_id=turn_id,
            role="assistant",
            text=normalized,
            now_ms=now_ms,
            stage=stage,
            trace_id=trace_id,
            question_id=question_id,
            topic_name=topic_name,
        )

    def append_candidate_answer(self, *, turn_id: str, answer_text: str, now_ms: int) -> bool:
        normalized = self._normalize_text(answer_text)
        if not normalized:
            return False

        pending = self.pending_turn
        appended = self.append_turn(
            turn_id=turn_id,
            role="user",
            text=normalized,
            now_ms=now_ms,
            stage=pending.stage,
            trace_id=pending.trace_id,
            question_id=pending.question_id,
            topic_name=pending.topic_name,
        )
        self.pending_turn = PendingTurn()
        return appended

    def trim_recent_turns(self) -> None:
        max_turns = max(2, int(self.max_turns or 8))
        if len(self.recent_turns) > max_turns:
            self.recent_turns = self.recent_turns[-max_turns:]

    def sync_runtime_state(
        self,
        *,
        focus_experience: str = "",
        focus_module: str = "",
        active_topic_name: str = "",
        active_topic_rounds: int = 0,
        topic_aliases: list[str] | None = None,
    ) -> None:
        self.focus_experience = str(focus_experience or self.focus_experience or "").strip()[: self.max_turn_text_chars]
        self.focus_module = str(focus_module or self.focus_module or "").strip()[: self.max_turn_text_chars]
        self.active_topic_name = str(active_topic_name or self.active_topic_name or "").strip()[:80]
        self.active_topic_rounds = max(0, int(active_topic_rounds or 0))

        if self.active_topic_name and self.active_topic_name not in self.known_entities:
            self.known_entities.append(self.active_topic_name)

        aliases = [str(item).strip() for item in (topic_aliases or []) if str(item).strip()]
        if aliases and self.active_topic_name:
            known = self.entity_aliases.setdefault(self.active_topic_name, [])
            for alias in aliases:
                if alias not in known:
                    known.append(alias)
                if alias not in self.known_entities:
                    self.known_entities.append(alias)

        self.version += 1

    def build_recent_history_text(self) -> str:
        if not self.recent_turns:
            return ""

        lines: list[str] = []
        for item in self.recent_turns[-self.max_turns :]:
            speaker = "面试官" if item.role == "assistant" else "候选人"
            topic_suffix = f" [{item.topic_name}]" if item.topic_name else ""
            lines.append(f"{speaker}{topic_suffix}: {item.text}")
        if not lines:
            return ""

        context_lines = [
            "### Runtime Context ###",
            f"focus_experience: {self.focus_experience or 'n/a'}",
            f"focus_module: {self.focus_module or 'n/a'}",
            f"active_topic: {self.active_topic_name or 'n/a'}",
            f"active_topic_rounds: {self.active_topic_rounds}",
        ]
        return "\n".join(context_lines) + "\n\n### Recent Stable Dialogue ###\n" + "\n".join(lines) + "\n\n"

    def get_last_assistant_question(self) -> str:
        if self.pending_turn.question_text:
            return self.pending_turn.question_text
        for item in reversed(self.recent_turns):
            if item.role == "assistant":
                return item.text
        return ""

    def snapshot(self) -> dict:
        return {
            "session_id": self.session_id,
            "version": self.version,
            "recent_turns_count": len(self.recent_turns),
            "recent_turns": [asdict(turn) for turn in self.recent_turns],
            "pending_turn": asdict(self.pending_turn),
            "focus_experience": self.focus_experience,
            "focus_module": self.focus_module,
            "active_topic_name": self.active_topic_name,
            "active_topic_rounds": self.active_topic_rounds,
            "known_entities": list(self.known_entities),
            "entity_aliases": dict(self.entity_aliases),
        }

    def _normalize_text(self, text: str) -> str:
        normalized = str(text or "").strip()
        if not normalized:
            return ""
        return normalized[: self.max_turn_text_chars]
