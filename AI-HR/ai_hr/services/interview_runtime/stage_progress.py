"""Stage signal extraction and completion tracking for early interview stages."""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True, slots=True)
class StageProgressSnapshot:
    """Snapshot of stage evidence after one update."""

    stage: str
    completed: bool
    collected_signals: list[str]
    missing_signals: list[str]
    confidence: float
    reason: str


class StageProgressEngine:
    """Track cumulative completion signals for S2 and S3."""

    _S2_SIGNAL_HINTS: dict[str, tuple[str, ...]] = {
        "education_anchor": (
            "\u5b66\u9662",
            "\u5b66\u6821",
            "\u5927\u4e09",
            "\u5927\u56db",
            "\u7814\u4e00",
            "\u5e94\u5c4a",
            "\u5b66\u751f",
            "\u4e13\u4e1a",
        ),
        "recent_experience": (
            "\u6700\u8fd1",
            "\u76ee\u524d",
            "\u5f53\u524d",
            "\u73b0\u5728",
            "\u8fd9\u6bb5\u65f6\u95f4",
            "\u8fd9\u4e00\u6bb5",
        ),
        "project_anchor": (
            "\u9879\u76ee",
            "\u5e73\u53f0",
            "\u7cfb\u7edf",
            "\u4e1a\u52a1",
            "\u505a\u8fc7",
            "\u53c2\u4e0e",
        ),
        "role_or_responsibility": (
            "\u8d1f\u8d23",
            "\u4e3b\u8981\u505a",
            "\u6211\u505a\u7684",
            "\u6211\u8d1f\u8d23",
            "\u72ec\u7acb",
            "\u53c2\u4e0e",
            "\u804c\u8d23",
        ),
        "tech_direction": (
            "java",
            "python",
            "spring",
            "mysql",
            "redis",
            "\u540e\u7aef",
            "\u5f00\u53d1",
            "\u6280\u672f\u6808",
        ),
    }

    _S3_CORE_STACK_HINTS = ("java", "spring", "spring boot", "mysql", "redis", "python", "mq", "rocketmq", "kafka")
    _S3_MIDDLEWARE_HINTS = ("redis", "mysql", "mq", "rocketmq", "kafka", "rabbitmq", "es", "elasticsearch", "seata")
    _S3_JD_GAP_HINTS = (
        "\u5e76\u53d1",
        "\u6027\u80fd",
        "\u6392\u67e5",
        "\u6545\u969c",
        "\u7a33\u5b9a\u6027",
        "\u67b6\u6784",
        "\u7f13\u5b58",
        "\u4e8b\u52a1",
        "\u7d22\u5f15",
        "\u9501",
    )
    _S3_USAGE_HINTS = (
        "\u7528\u5728",
        "\u5e94\u7528\u5728",
        "\u8d1f\u8d23",
        "\u505a\u4e86",
        "\u5904\u7406",
        "\u89e3\u51b3",
        "\u4f18\u5316",
        "\u573a\u666f",
        "\u8bbe\u8ba1",
        "\u9009\u578b",
    )

    def update(self, *, state: dict, stage: str, transcript: str) -> tuple[dict, StageProgressSnapshot | None]:
        normalized_stage = str(stage or "")
        if normalized_stage not in {"S2", "S3"}:
            return state, None

        merged = dict(state)
        progress = dict(merged.get("stage_progress") or {})
        stage_state = dict(progress.get(normalized_stage) or {})

        if normalized_stage == "S2":
            stage_state = self._update_s2(stage_state=stage_state, transcript=transcript)
            snapshot = self._snapshot_s2(stage_state=stage_state)
        else:
            stage_state = self._update_s3(stage_state=stage_state, transcript=transcript)
            snapshot = self._snapshot_s3(stage_state=stage_state)

        progress[normalized_stage] = stage_state
        merged["stage_progress"] = progress
        merged["missing_evidence"] = list(snapshot.missing_signals)
        merged["transition_reason"] = snapshot.reason
        return merged, snapshot

    def _update_s2(self, *, stage_state: dict, transcript: str) -> dict:
        text = str(transcript or "")
        lowered = text.lower()
        updated = {
            "education_anchor": bool(stage_state.get("education_anchor")),
            "recent_experience": bool(stage_state.get("recent_experience")),
            "project_anchor": bool(stage_state.get("project_anchor")),
            "role_or_responsibility": bool(stage_state.get("role_or_responsibility")),
            "tech_direction": bool(stage_state.get("tech_direction")),
        }
        for signal, hints in self._S2_SIGNAL_HINTS.items():
            if updated[signal]:
                continue
            if any(hint in lowered or hint in text for hint in hints):
                updated[signal] = True
        return updated

    def _snapshot_s2(self, *, stage_state: dict) -> StageProgressSnapshot:
        collected = [key for key, value in stage_state.items() if value]
        missing = [key for key in self._S2_SIGNAL_HINTS if not stage_state.get(key)]
        strong_core = stage_state.get("project_anchor") and stage_state.get("role_or_responsibility")
        completed = len(collected) >= 3 and strong_core
        confidence = min(1.0, len(collected) / 4.0)
        reason = "s2_signals_completed" if completed else "s2_missing_intro_evidence"
        return StageProgressSnapshot(
            stage="S2",
            completed=completed,
            collected_signals=collected,
            missing_signals=missing,
            confidence=confidence,
            reason=reason,
        )

    def _update_s3(self, *, stage_state: dict, transcript: str) -> dict:
        text = str(transcript or "")
        lowered = text.lower()
        core_hits = set(stage_state.get("core_stack_hits") or [])
        middleware_hits = set(stage_state.get("middleware_hits") or [])
        jd_hits = set(stage_state.get("jd_hits") or [])
        usage_evidence = int(stage_state.get("usage_evidence_count") or 0)

        for hint in self._S3_CORE_STACK_HINTS:
            if hint in lowered:
                core_hits.add(hint)
        for hint in self._S3_MIDDLEWARE_HINTS:
            if hint in lowered:
                middleware_hits.add(hint)
        for hint in self._S3_JD_GAP_HINTS:
            if hint in lowered or hint in text:
                jd_hits.add(hint)
        if any(hint in lowered or hint in text for hint in self._S3_USAGE_HINTS):
            usage_evidence += 1

        return {
            "core_stack_hits": sorted(core_hits),
            "middleware_hits": sorted(middleware_hits),
            "jd_hits": sorted(jd_hits),
            "usage_evidence_count": min(5, usage_evidence),
        }

    def _snapshot_s3(self, *, stage_state: dict) -> StageProgressSnapshot:
        core_hits = list(stage_state.get("core_stack_hits") or [])
        middleware_hits = list(stage_state.get("middleware_hits") or [])
        jd_hits = list(stage_state.get("jd_hits") or [])
        usage_evidence = int(stage_state.get("usage_evidence_count") or 0)

        collected: list[str] = []
        if len(core_hits) >= 2:
            collected.append("core_stack_verified")
        if middleware_hits:
            collected.append("middleware_real_usage")
        if usage_evidence >= 1:
            collected.append("real_usage_evidence")
        if jd_hits:
            collected.append("jd_gap_covered")

        missing: list[str] = []
        if len(core_hits) < 2:
            missing.append("core_stack_verified")
        if not middleware_hits:
            missing.append("middleware_real_usage")
        if usage_evidence < 1:
            missing.append("real_usage_evidence")
        if not jd_hits:
            missing.append("jd_gap_covered")

        completed = len(core_hits) >= 2 and bool(middleware_hits) and usage_evidence >= 1 and bool(jd_hits)
        confidence = min(
            1.0,
            (min(2, len(core_hits)) * 0.25) +
            (0.25 if middleware_hits else 0.0) +
            (0.25 if usage_evidence >= 1 else 0.0) +
            (0.25 if jd_hits else 0.0),
        )
        reason = "s3_signals_completed" if completed else "s3_missing_stack_evidence"
        return StageProgressSnapshot(
            stage="S3",
            completed=completed,
            collected_signals=collected,
            missing_signals=missing,
            confidence=confidence,
            reason=reason,
        )
