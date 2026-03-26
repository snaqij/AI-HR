from __future__ import annotations

from scripts.realtime_e2e_benchmark import BenchmarkStats, _evaluate_sla, _report, percentile


def test_percentile_should_return_expected_value() -> None:
    values = [10, 20, 30, 40, 50]
    assert percentile(values, 0.5) == 30.0
    assert percentile(values, 0.95) == 50.0


def test_percentile_should_handle_empty_values() -> None:
    assert percentile([], 0.5) == 0.0


def test_report_should_include_p99_ack_and_loss() -> None:
    stats = BenchmarkStats(
        asr_ms=[100, 120, 140],
        llm_ms=[20, 30, 40],
        tts_ms=[180, 200, 220],
        e2e_ms=[320, 350, 380],
        ack_ms=[2, 3, 5],
        duplicate_count=1,
        server_drop_count=1,
        sent_frames=10,
        ingest_success_count=10,
        tts_published_count=9,
        webhook_accepted_count=2,
    )
    report = _report(stats)
    assert report["asr"]["p99"] == 140.0
    assert report["ack"]["p95"] == 5.0
    assert report["loss"]["duplicate_count"] == 1
    assert report["loss"]["drop_rate"] == 0.1
    assert report["room_ingest"]["ingest_success_rate"] == 1.0
    assert report["room_ingest"]["tts_published_rate"] == 0.9
    assert report["room_ingest"]["webhook_accepted_count"] == 2


def test_evaluate_sla_should_return_pass_when_all_targets_met() -> None:
    report = {
        "asr": {"p95": 600},
        "llm": {"p95": 700},
        "tts": {"p95": 900},
        "e2e": {"p95": 1600},
        "room_ingest": {"ingest_success_rate": 1.0, "tts_published_rate": 0.98},
    }
    result = _evaluate_sla(
        report,
        asr_p95_max=800,
        llm_p95_max=900,
        tts_p95_max=1200,
        e2e_p95_max=2000,
        min_ingest_success_rate=0.95,
        min_tts_publish_rate=0.95,
    )
    assert result["pass"] is True
    assert all(result["checks"].values()) is True
