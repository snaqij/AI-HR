"""AI 面试官压测脚本骨架。

用法示例：
python scripts/ai_interview_load_test.py --base-url http://127.0.0.1:8000 --api-prefix /api/v1 --concurrency 20 --rounds 5
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed


def _request(method: str, url: str, payload: dict | None = None) -> tuple[int, dict]:
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url=url, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
            return int(resp.status), json.loads(body)
    except urllib.error.HTTPError as exc:
        try:
            return int(exc.code), json.loads(exc.read().decode("utf-8"))
        except Exception:
            return int(exc.code), {"error": {"message": str(exc)}}


def _percentile(values: list[int], p: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    k = max(0, min(len(values) - 1, int(round((p / 100.0) * (len(values) - 1)))))
    return float(sorted(values)[k])


def _prepare_seed_data(base_url: str, api_prefix: str) -> tuple[str, str]:
    status, job_resp = _request(
        "POST",
        f"{base_url}{api_prefix}/jobs",
        {
            "title": "Load Test Interview Engineer",
            "department": "Engineering",
            "city": "Shanghai",
            "salary_range": "35k-55k",
            "requirements": "Python FastAPI distributed systems",
        },
    )
    if status >= 300:
        raise RuntimeError(f"create job failed: {job_resp}")
    job_id = job_resp["data"]["id"]

    status, candidate_resp = _request(
        "POST",
        f"{base_url}{api_prefix}/candidates/import",
        {
            "candidates": [
                {
                    "name": "Load Candidate",
                    "source_channel": "boss",
                    "external_candidate_id": f"load-candidate-{int(time.time())}",
                    "resume_text": "Python FastAPI MySQL",
                    "raw_profile": {"skills": ["Python", "FastAPI"]},
                }
            ]
        },
    )
    if status >= 300:
        raise RuntimeError(f"create candidate failed: {candidate_resp}")
    candidate_id = candidate_resp["data"]["candidates"][0]["id"]
    return job_id, candidate_id


def _run_single_session(
    *,
    base_url: str,
    api_prefix: str,
    job_id: str,
    candidate_id: str,
    rounds: int,
    index: int,
) -> dict:
    started_at = time.perf_counter()
    status, create_resp = _request(
        "POST",
        f"{base_url}{api_prefix}/ai/interviews/sessions",
        {
            "candidate_id": candidate_id,
            "job_id": job_id,
            "payload": {"model_route_policy": random.choice(["cost_first", "balanced", "quality_first"])},
        },
    )
    if status >= 300:
        return {"ok": False, "error": f"create_session_failed:{status}"}
    session_id = create_resp["data"]["session"]["id"]

    status, _ = _request("POST", f"{base_url}{api_prefix}/ai/interviews/sessions/{session_id}/start", {"operator": "load_tester"})
    if status >= 300:
        return {"ok": False, "error": f"start_failed:{status}"}

    turn_latencies: list[int] = []
    for turn in range(rounds):
        event_begin = time.perf_counter()
        status, event_resp = _request(
            "POST",
            f"{base_url}{api_prefix}/ai/interviews/sessions/{session_id}/events",
            {
                "event_id": f"load-{index}-{turn}",
                "seq": turn + 1,
                "speaker": "candidate",
                "transcript": f"load answer {turn}",
                "confidence": 0.86,
                "latency_ms": 600,
            },
        )
        turn_cost_ms = int((time.perf_counter() - event_begin) * 1000)
        turn_latencies.append(turn_cost_ms)
        if status >= 300:
            return {"ok": False, "error": f"event_failed:{status}", "turn_latencies": turn_latencies}
        _ = event_resp

    _request(
        "POST",
        f"{base_url}{api_prefix}/ai/interviews/sessions/{session_id}/finish",
        {"result_status": "completed", "operator": "load_tester"},
    )
    _request("GET", f"{base_url}{api_prefix}/ai/interviews/sessions/{session_id}/report")
    total_cost_ms = int((time.perf_counter() - started_at) * 1000)
    return {
        "ok": True,
        "session_id": session_id,
        "total_latency_ms": total_cost_ms,
        "turn_latencies": turn_latencies,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="AI 面试官压测脚本骨架")
    parser.add_argument("--base-url", required=True, help="服务地址，如 http://127.0.0.1:8000")
    parser.add_argument("--api-prefix", default="/api/v1")
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--sessions", type=int, default=50)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--target-e2e-p95-ms", type=int, default=1800)
    args = parser.parse_args()

    job_id, candidate_id = _prepare_seed_data(args.base_url, args.api_prefix)
    lock = threading.Lock()
    results: list[dict] = []

    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        futures = [
            pool.submit(
                _run_single_session,
                base_url=args.base_url,
                api_prefix=args.api_prefix,
                job_id=job_id,
                candidate_id=candidate_id,
                rounds=args.rounds,
                index=index,
            )
            for index in range(args.sessions)
        ]
        for future in as_completed(futures):
            result = future.result()
            with lock:
                results.append(result)

    ok_results = [item for item in results if item.get("ok")]
    fail_results = [item for item in results if not item.get("ok")]
    all_turn_latencies = [lat for item in ok_results for lat in item.get("turn_latencies", [])]
    e2e_p95 = _percentile(all_turn_latencies, 95)
    e2e_avg = float(statistics.mean(all_turn_latencies)) if all_turn_latencies else 0.0

    summary = {
        "total_sessions": args.sessions,
        "success_sessions": len(ok_results),
        "failed_sessions": len(fail_results),
        "turn_count": len(all_turn_latencies),
        "turn_latency_avg_ms": round(e2e_avg, 2),
        "turn_latency_p95_ms": round(e2e_p95, 2),
        "target_e2e_p95_ms": args.target_e2e_p95_ms,
        "target_met": bool(e2e_p95 <= args.target_e2e_p95_ms),
        "sample_failures": fail_results[:5],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
