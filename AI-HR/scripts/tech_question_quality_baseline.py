from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import desc, select

from ai_hr.db.models import AIInterviewQuestionSet, AIInterviewSession, AIInterviewTurn, Candidate, Job
from ai_hr.db.session import SessionLocal

TECH_DIMENSIONS: tuple[str, ...] = (
    "project_experience",
    "problem_solving",
    "system_design",
    "coding",
    "performance",
    "reliability",
    "ownership",
    "communication",
    "job_fit",
)

EN_STOPWORDS: set[str] = {
    "about",
    "after",
    "also",
    "and",
    "are",
    "been",
    "between",
    "but",
    "can",
    "did",
    "for",
    "from",
    "have",
    "how",
    "into",
    "its",
    "just",
    "more",
    "not",
    "our",
    "that",
    "the",
    "their",
    "them",
    "then",
    "they",
    "this",
    "those",
    "use",
    "used",
    "using",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "with",
    "would",
    "your",
}

ZH_TECH_TERMS: tuple[str, ...] = (
    "性能",
    "并发",
    "架构",
    "系统设计",
    "数据库",
    "缓存",
    "消息队列",
    "稳定性",
    "可用性",
    "扩展性",
    "故障",
    "排查",
    "监控",
    "指标",
    "压测",
    "容量",
    "一致性",
    "事务",
    "幂等",
    "降级",
)


def percentile(values: list[int], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, min(len(ordered), int(len(ordered) * p + 0.9999)))
    return float(ordered[rank - 1])


def _normalize_text(text: str) -> str:
    folded = re.sub(r"\s+", " ", (text or "").strip()).lower()
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", folded)


def _safe_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed >= 0 else None


def compute_duplicate_rate(questions: list[dict[str, Any]]) -> float:
    normalized_questions = []
    for item in questions:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_text(str(item.get("question") or ""))
        if normalized:
            normalized_questions.append(normalized)
    total = len(normalized_questions)
    if total == 0:
        return 0.0
    unique = len(set(normalized_questions))
    return round((total - unique) / total, 4)


def extract_target_keywords(
    *,
    job_requirements: str,
    skills: list[str],
    resume_text: str,
    max_keywords: int = 18,
) -> list[str]:
    merged_text = f"{job_requirements or ''} {job_requirements or ''} {(resume_text or '')[:2500]}".lower()
    keywords: list[str] = []
    seen: set[str] = set()

    for skill in skills or []:
        token = str(skill or "").strip().lower()
        if not token or token in seen:
            continue
        seen.add(token)
        keywords.append(token)
        if len(keywords) >= max_keywords:
            return keywords

    english_tokens = re.findall(r"[a-z][a-z0-9_+\-.]{2,24}", merged_text)
    token_counter = Counter(token for token in english_tokens if token not in EN_STOPWORDS)
    for token, _ in token_counter.most_common(max_keywords):
        if token in seen:
            continue
        seen.add(token)
        keywords.append(token)
        if len(keywords) >= max_keywords:
            return keywords

    for term in ZH_TECH_TERMS:
        if term in merged_text and term not in seen:
            seen.add(term)
            keywords.append(term)
            if len(keywords) >= max_keywords:
                return keywords
    return keywords


def compute_dimension_coverage(questions: list[dict[str, Any]]) -> float:
    if not questions:
        return 0.0
    dimensions = {
        str(item.get("dimension") or "").strip().lower()
        for item in questions
        if isinstance(item, dict) and str(item.get("question") or "").strip()
    }
    hit_count = len(dimensions.intersection(TECH_DIMENSIONS))
    denominator = min(max(1, len(questions)), len(TECH_DIMENSIONS))
    return round(hit_count / denominator, 4)


def compute_keyword_coverage(questions: list[dict[str, Any]], keywords: list[str]) -> float:
    if not keywords:
        return 1.0
    merged = []
    for item in questions:
        if not isinstance(item, dict):
            continue
        merged.append(str(item.get("question") or ""))
        merged.append(str(item.get("expected_signal") or ""))
        merged.append(str(item.get("followup_condition") or ""))
    blob = " ".join(merged).lower()
    if not blob.strip():
        return 0.0
    hit_count = sum(1 for keyword in keywords if keyword and keyword in blob)
    return round(hit_count / len(keywords), 4)


def _extract_turn_latency_ms(turn: dict[str, Any]) -> int | None:
    payload = turn.get("payload")
    if isinstance(payload, dict):
        breakdown = payload.get("latency_breakdown")
        if isinstance(breakdown, dict):
            e2e_ms = _safe_int(breakdown.get("e2e_ms"))
            if e2e_ms is not None:
                return e2e_ms
    return _safe_int(turn.get("latency_ms"))


def build_session_metric(
    *,
    session_id: str,
    questions: list[dict[str, Any]],
    candidate_turns: list[dict[str, Any]],
    job_requirements: str,
    skills: list[str],
    resume_text: str,
) -> dict[str, Any]:
    question_count = len([item for item in questions if isinstance(item, dict) and str(item.get("question") or "").strip()])
    candidate_turn_count = len(candidate_turns)

    keywords = extract_target_keywords(
        job_requirements=job_requirements,
        skills=skills,
        resume_text=resume_text,
    )
    dimension_coverage_rate = compute_dimension_coverage(questions)
    keyword_coverage_rate = compute_keyword_coverage(questions, keywords)
    coverage_rate = round(dimension_coverage_rate * 0.55 + keyword_coverage_rate * 0.45, 4)

    duplication_rate = compute_duplicate_rate(questions)
    explicit_followup_turns = 0
    for turn in candidate_turns:
        flags = turn.get("policy_flags") or []
        if isinstance(flags, list) and any(str(flag) == "insufficient_evidence" for flag in flags):
            explicit_followup_turns += 1
    estimated_followup_turns = max(0, candidate_turn_count - question_count)
    followup_turns = max(explicit_followup_turns, estimated_followup_turns)
    followup_depth = round(followup_turns / max(1, question_count), 4) if question_count > 0 else 0.0

    latency_values: list[int] = []
    for turn in candidate_turns:
        latency_ms = _extract_turn_latency_ms(turn)
        if latency_ms is not None:
            latency_values.append(latency_ms)
    avg_latency_ms = round(float(statistics.fmean(latency_values)), 2) if latency_values else 0.0

    return {
        "session_id": session_id,
        "question_count": question_count,
        "candidate_turn_count": candidate_turn_count,
        "coverage_rate": coverage_rate,
        "dimension_coverage_rate": dimension_coverage_rate,
        "keyword_coverage_rate": keyword_coverage_rate,
        "duplication_rate": duplication_rate,
        "followup_depth": followup_depth,
        "followup_turns": followup_turns,
        "explicit_followup_turns": explicit_followup_turns,
        "estimated_followup_turns": estimated_followup_turns,
        "avg_response_latency_ms": avg_latency_ms,
        "latency_p95_ms": round(percentile(latency_values, 0.95), 2) if latency_values else 0.0,
        "latency_sample_count": len(latency_values),
    }


def _build_session_query(*, session_ids: list[str] | None, window_hours: float, limit: int):
    if session_ids:
        unique_ids = list(dict.fromkeys([item.strip() for item in session_ids if item and item.strip()]))
        stmt = select(AIInterviewSession).where(AIInterviewSession.id.in_(unique_ids))
        return stmt, unique_ids
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=max(0.1, float(window_hours)))
    stmt = (
        select(AIInterviewSession)
        .where(AIInterviewSession.created_at >= since)
        .order_by(desc(AIInterviewSession.created_at))
        .limit(max(1, int(limit)))
    )
    return stmt, []


def evaluate_quality_baseline(*, session_ids: list[str] | None, window_hours: float, limit: int) -> dict[str, Any]:
    with SessionLocal() as db:
        stmt, requested_ids = _build_session_query(session_ids=session_ids, window_hours=window_hours, limit=limit)
        sessions = list(db.execute(stmt).scalars().all())
        if requested_ids:
            by_id = {item.id: item for item in sessions}
            sessions = [by_id[item] for item in requested_ids if item in by_id][: max(1, int(limit))]

        if not sessions:
            return {
                "generated_at": datetime.now(UTC).isoformat(),
                "window_hours": window_hours,
                "session_count": 0,
                "summary": {},
                "sessions": [],
            }

        session_ids_in_scope = [item.id for item in sessions]
        candidate_ids = {item.candidate_id for item in sessions}
        job_ids = {item.job_id for item in sessions}

        candidates = list(db.execute(select(Candidate).where(Candidate.id.in_(candidate_ids))).scalars().all())
        jobs = list(db.execute(select(Job).where(Job.id.in_(job_ids))).scalars().all())
        candidate_map = {item.id: item for item in candidates}
        job_map = {item.id: item for item in jobs}

        question_rows = list(
            db.execute(
                select(AIInterviewQuestionSet)
                .where(AIInterviewQuestionSet.session_id.in_(session_ids_in_scope))
                .order_by(
                    AIInterviewQuestionSet.session_id.asc(),
                    AIInterviewQuestionSet.version.desc(),
                    AIInterviewQuestionSet.created_at.desc(),
                )
            )
            .scalars()
            .all()
        )
        latest_question_set_map: dict[str, AIInterviewQuestionSet] = {}
        for row in question_rows:
            if row.session_id not in latest_question_set_map:
                latest_question_set_map[row.session_id] = row

        turn_rows = list(
            db.execute(
                select(AIInterviewTurn)
                .where(AIInterviewTurn.session_id.in_(session_ids_in_scope))
                .where(AIInterviewTurn.speaker == "candidate")
                .order_by(AIInterviewTurn.session_id.asc(), AIInterviewTurn.turn_no.asc())
            )
            .scalars()
            .all()
        )
        turns_by_session: dict[str, list[AIInterviewTurn]] = defaultdict(list)
        for row in turn_rows:
            turns_by_session[row.session_id].append(row)

        session_metrics: list[dict[str, Any]] = []
        overall_latency_samples: list[int] = []
        for session in sessions:
            question_set = latest_question_set_map.get(session.id)
            questions = question_set.questions_json if question_set is not None and isinstance(question_set.questions_json, list) else []
            raw_turns = turns_by_session.get(session.id, [])
            serialized_turns = [
                {
                    "policy_flags": list(item.policy_flags or []),
                    "payload": dict(item.payload or {}),
                    "latency_ms": item.latency_ms,
                }
                for item in raw_turns
            ]

            candidate = candidate_map.get(session.candidate_id)
            job = job_map.get(session.job_id)
            skills = []
            if candidate is not None and isinstance(candidate.raw_profile, dict):
                raw_skills = candidate.raw_profile.get("skills", [])
                if isinstance(raw_skills, list):
                    skills = [str(item) for item in raw_skills]

            metric = build_session_metric(
                session_id=session.id,
                questions=questions,
                candidate_turns=serialized_turns,
                job_requirements=job.requirements if job is not None else "",
                skills=skills,
                resume_text=candidate.resume_text if candidate is not None and candidate.resume_text else "",
            )
            for item in serialized_turns:
                latency_ms = _extract_turn_latency_ms(item)
                if latency_ms is not None:
                    overall_latency_samples.append(latency_ms)
            metric["language"] = session.language
            metric["status"] = session.status
            metric["created_at"] = session.created_at.isoformat() if session.created_at else None
            session_metrics.append(metric)

        coverage_values = [item["coverage_rate"] for item in session_metrics]
        dimension_values = [item["dimension_coverage_rate"] for item in session_metrics]
        keyword_values = [item["keyword_coverage_rate"] for item in session_metrics]
        duplication_values = [item["duplication_rate"] for item in session_metrics]
        followup_values = [item["followup_depth"] for item in session_metrics]

        summary = {
            "coverage_rate_avg": round(float(statistics.fmean(coverage_values)), 4) if coverage_values else 0.0,
            "dimension_coverage_rate_avg": round(float(statistics.fmean(dimension_values)), 4) if dimension_values else 0.0,
            "keyword_coverage_rate_avg": round(float(statistics.fmean(keyword_values)), 4) if keyword_values else 0.0,
            "duplication_rate_avg": round(float(statistics.fmean(duplication_values)), 4) if duplication_values else 0.0,
            "followup_depth_avg": round(float(statistics.fmean(followup_values)), 4) if followup_values else 0.0,
            "avg_response_latency_ms": round(float(statistics.fmean(overall_latency_samples)), 2) if overall_latency_samples else 0.0,
            "response_latency_p95_ms": round(percentile(overall_latency_samples, 0.95), 2) if overall_latency_samples else 0.0,
            "turn_sample_count": len(overall_latency_samples),
        }

        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "window_hours": window_hours,
            "session_count": len(session_metrics),
            "summary": summary,
            "sessions": session_metrics,
        }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Technical interview question quality baseline evaluator")
    parser.add_argument("--window-hours", type=float, default=72.0, help="lookback window when session ids are not provided")
    parser.add_argument(
        "--session-id",
        action="append",
        dest="session_ids",
        default=[],
        help="target interview session id, can be repeated",
    )
    parser.add_argument("--limit", type=int, default=200, help="max sessions in report")
    parser.add_argument("--output", type=str, default="", help="optional path to write json report")
    parser.add_argument("--session-detail-limit", type=int, default=30, help="max session details printed in stdout")
    parser.add_argument("--compact", action="store_true", help="print compact json")
    return parser.parse_args()


def _build_stdout_payload(*, report: dict[str, Any], session_detail_limit: int) -> dict[str, Any]:
    payload = {
        "generated_at": report.get("generated_at"),
        "window_hours": report.get("window_hours"),
        "session_count": report.get("session_count"),
        "summary": report.get("summary", {}),
        "sessions": [],
    }
    sessions = report.get("sessions", [])
    if isinstance(sessions, list):
        payload["sessions"] = sessions[: max(0, int(session_detail_limit))]
    return payload


def main() -> int:
    args = _parse_args()
    report = evaluate_quality_baseline(
        session_ids=args.session_ids,
        window_hours=max(0.1, float(args.window_hours)),
        limit=max(1, int(args.limit)),
    )
    output_payload = _build_stdout_payload(
        report=report,
        session_detail_limit=max(0, int(args.session_detail_limit)),
    )
    serialized_stdout = json.dumps(output_payload, ensure_ascii=False, separators=(",", ":")) if args.compact else json.dumps(output_payload, ensure_ascii=False, indent=2)
    print(serialized_stdout)

    if args.output:
        out_path = Path(args.output).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"full report written to: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
