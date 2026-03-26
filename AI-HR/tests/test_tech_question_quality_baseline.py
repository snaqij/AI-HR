from __future__ import annotations

from scripts.tech_question_quality_baseline import (
    build_session_metric,
    compute_duplicate_rate,
    compute_keyword_coverage,
    extract_target_keywords,
)


def test_compute_duplicate_rate_should_merge_punctuation_variants() -> None:
    questions = [
        {"question": "请介绍你做过的缓存优化方案？"},
        {"question": "请 介绍 你 做过 的 缓存优化方案!"},
        {"question": "说说一次线上故障排查"},
    ]
    assert compute_duplicate_rate(questions) == 0.3333


def test_extract_target_keywords_should_include_skills_and_job_terms() -> None:
    keywords = extract_target_keywords(
        job_requirements="负责高并发服务治理与性能优化，熟悉 Python/Kafka。",
        skills=["Python", "Kafka", "MySQL"],
        resume_text="做过链路压测、数据库索引优化和故障演练。",
        max_keywords=12,
    )
    lowered = {item.lower() for item in keywords}
    assert "python" in lowered
    assert "kafka" in lowered
    assert "mysql" in lowered


def test_compute_keyword_coverage_should_count_hits_from_question_payload() -> None:
    questions = [
        {"question": "你是如何做 Python 服务性能优化的？", "expected_signal": "包含吞吐提升与延迟下降指标"},
        {"question": "讲一次 Kafka 积压排查案例", "followup_condition": "说明根因与恢复步骤"},
    ]
    keywords = ["python", "kafka", "mysql"]
    assert compute_keyword_coverage(questions, keywords) == 0.6667


def test_build_session_metric_should_calculate_followup_and_latency() -> None:
    questions = [
        {"question": "Q1", "dimension": "problem_solving"},
        {"question": "Q2", "dimension": "system_design"},
        {"question": "Q3", "dimension": "project_experience"},
    ]
    candidate_turns = [
        {"policy_flags": [], "payload": {"latency_breakdown": {"e2e_ms": 700}}, "latency_ms": 900},
        {"policy_flags": ["insufficient_evidence"], "payload": {"latency_breakdown": {"e2e_ms": 800}}, "latency_ms": 950},
        {"policy_flags": [], "payload": {}, "latency_ms": 1000},
        {"policy_flags": [], "payload": {}, "latency_ms": 1100},
        {"policy_flags": [], "payload": {}, "latency_ms": 1200},
    ]
    metric = build_session_metric(
        session_id="s-1",
        questions=questions,
        candidate_turns=candidate_turns,
        job_requirements="负责系统设计与性能优化",
        skills=["python"],
        resume_text="做过高并发系统改造",
    )
    assert metric["question_count"] == 3
    assert metric["candidate_turn_count"] == 5
    assert metric["estimated_followup_turns"] == 2
    assert metric["followup_depth"] == 0.6667
    assert metric["avg_response_latency_ms"] == 960.0
