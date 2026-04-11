"""Shared question-pack normalization helpers."""

from __future__ import annotations

from typing import Any

from ai_hr.domain.constants import InterviewStage


def _normalize_text_list(raw: Any) -> list[str]:
    if isinstance(raw, str):
        parts = raw.replace("，", ",").replace("、", ",").split(",")
        return [item.strip() for item in parts if item and item.strip()]
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def normalize_question_stage(stage: str, dimension: str) -> str:
    candidate = str(stage or "").strip()
    if candidate in {
        InterviewStage.OPENING,
        InterviewStage.SELF_INTRO,
        InterviewStage.TECH_STACK,
        InterviewStage.PROJECT_DEEP_DIVE,
        InterviewStage.JD_MATCH,
        InterviewStage.GENERAL_PROBE,
        InterviewStage.COMPANY_QA,
        InterviewStage.CLOSING,
    }:
        return candidate

    dim = str(dimension or "").strip().lower()
    if dim in {"self_intro"}:
        return InterviewStage.SELF_INTRO
    if dim in {"focus_experience", "focus_module", "stack_verification", "core_stack_validation", "middleware_usage"}:
        return InterviewStage.TECH_STACK
    if dim in {"project_deep_dive", "project_tradeoff", "system_design"}:
        return InterviewStage.PROJECT_DEEP_DIVE
    if dim in {"experience_validation", "jd_match", "jd_readiness", "jd_gap_analysis"}:
        return InterviewStage.JD_MATCH
    if dim in {"capability_probe", "performance_troubleshooting", "problem_solving"}:
        return InterviewStage.GENERAL_PROBE
    if dim in {"company_qa"}:
        return InterviewStage.COMPANY_QA
    return InterviewStage.TECH_STACK


def _derive_question_type(stage: str, raw_type: str) -> str:
    candidate = str(raw_type or "").strip().lower()
    if candidate in {"profile", "capability", "wrap_up"}:
        return candidate
    if stage in {InterviewStage.SELF_INTRO, InterviewStage.TECH_STACK}:
        return "profile"
    if stage in {InterviewStage.COMPANY_QA, InterviewStage.CLOSING}:
        return "wrap_up"
    return "capability"


def _derive_focus_slot(dimension: str, raw_slot: str) -> str:
    candidate = str(raw_slot or "").strip().lower()
    if candidate in {"experience", "module"}:
        return candidate
    dim = str(dimension or "").strip().lower()
    if dim == "focus_experience":
        return "experience"
    if dim == "focus_module":
        return "module"
    return ""


def _derive_bucket(stage: str, dimension: str, raw_bucket: str) -> str:
    candidate = str(raw_bucket or "").strip().lower()
    if candidate in {"profile", "stack", "scenario", "experience", "wrap_up"}:
        return candidate
    dim = str(dimension or "").strip().lower()
    if stage == InterviewStage.SELF_INTRO:
        return "profile"
    if stage in {InterviewStage.COMPANY_QA, InterviewStage.CLOSING}:
        return "wrap_up"
    if dim in {"performance_troubleshooting", "system_design", "scenario_design"}:
        return "scenario"
    if dim in {
        "focus_experience",
        "experience_validation",
        "jd_match",
        "jd_match_case",
        "jd_readiness",
        "jd_gap_analysis",
        "project_deep_dive",
        "project_tradeoff",
        "internship_experience",
        "project_experience",
    }:
        return "experience"
    return "stack"


def normalize_question_item(item: dict[str, Any] | object, *, default_index: int = 0) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None

    dimension = str(item.get("dimension") or "communication").strip() or "communication"
    stage = normalize_question_stage(str(item.get("stage") or ""), dimension)
    question = str(item.get("question") or "").strip()
    if not question:
        return None

    try:
        max_followups = int(item.get("max_followups") or 2)
    except (TypeError, ValueError):
        max_followups = 2

    question_type = _derive_question_type(stage, str(item.get("question_type") or ""))
    topic_name = str(item.get("topic_name") or dimension or f"topic_{default_index}").strip() or f"topic_{default_index}"
    topic_aliases = _normalize_text_list(item.get("topic_aliases"))
    focus_slot = _derive_focus_slot(dimension, str(item.get("focus_slot") or ""))
    focus_hint = str(item.get("focus_hint") or topic_name).strip()
    bucket = _derive_bucket(stage, dimension, str(item.get("bucket") or ""))
    raw_idx = item.get("idx")
    try:
        normalized_idx = max(1, int(raw_idx))
    except (TypeError, ValueError):
        normalized_idx = default_index + 1
    question_id = str(
        item.get("question_id")
        or item.get("id")
        or f"{stage.lower()}_{normalized_idx}"
    ).strip()

    success_signals = _normalize_text_list(item.get("success_signals"))
    if not success_signals:
        success_signals = _normalize_text_list(item.get("expected_signal"))

    return {
        "idx": normalized_idx,
        "question_id": question_id,
        "id": question_id,
        "question": question,
        "dimension": dimension,
        "question_type": question_type,
        "expected_signal": str(item.get("expected_signal") or "").strip(),
        "followup_condition": str(item.get("followup_condition") or "").strip(),
        "stage": stage,
        "max_followups": max(1, min(3, max_followups)),
        "success_signals": success_signals,
        "topic_name": topic_name,
        "topic_aliases": topic_aliases,
        "focus_slot": focus_slot,
        "focus_hint": focus_hint,
        "bucket": bucket,
        "target_skill": str(item.get("target_skill") or "").strip(),
        "source_evidence": str(item.get("source_evidence") or "").strip(),
    }


def normalize_question_pack(question_pack: dict[str, Any] | None) -> dict[str, Any]:
    pack = dict(question_pack or {})
    raw_questions = pack.get("questions", [])
    normalized_questions: list[tuple[int, int, dict[str, Any]]] = []
    if isinstance(raw_questions, list):
        for idx, raw in enumerate(raw_questions):
            normalized = normalize_question_item(raw, default_index=idx)
            if normalized is not None:
                normalized_questions.append((int(normalized.get("idx") or idx + 1), idx, normalized))
    normalized_questions.sort(key=lambda item: (item[0], item[1]))
    pack["questions"] = [item[2] for item in normalized_questions]
    pack["question_count"] = len(pack["questions"])
    return pack
