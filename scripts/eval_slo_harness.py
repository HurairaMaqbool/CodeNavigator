#!/usr/bin/env python3
# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""
scripts/eval_slo_harness.py
-------------------------
Run Evaluation module SLO measurements (5-run statistical checks).

Usage:
  python scripts/eval_slo_harness.py [--job-id JOB_ID] [--runs 5]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEFAULT_JOB = "375c63667dff3e1e20ef5712cf1c0cb33940a9b49644bb855f1f89fe959d9f4d"


def _latency(fn):
    t0 = time.perf_counter()
    try:
        result = fn()
        err = None
    except Exception as exc:
        result = None
        err = str(exc)
    return (time.perf_counter() - t0) * 1000, result, err


def measure_health(job_id: str, runs: int) -> dict:
    from eval.health_check import run_full_eval_precheck

    latencies = []
    oks = []
    for _ in range(runs):
        ms, res, err = _latency(lambda: run_full_eval_precheck(job_id, include_agent_probe=False))
        latencies.append(ms)
        oks.append(res.ok if res and not err else False)
    return {
        "component": "Index/Chunks/Probe health",
        "runs": runs,
        "latency_ms": {"p50": statistics.median(latencies), "max": max(latencies)},
        "ok_rate": f"{sum(oks)}/{runs}",
        "consistent": len(set(oks)) == 1,
    }


def measure_compare(runs: int) -> dict:
    from eval.compare_runs import compare_eval_runs, load_history

    records = load_history()
    if len(records) < 2:
        return {"component": "Compare versions", "skipped": "need >=2 history runs"}
    base = records[1].get("version") or records[1].get("run_id")
    cand = records[0].get("version") or records[0].get("run_id")
    counts = []
    latencies = []
    for _ in range(runs):
        ms, res, err = _latency(lambda: compare_eval_runs(base, cand))
        latencies.append(ms)
        counts.append(len(res.get("regressions") or []) if res and not err else -1)
    return {
        "component": "Compare versions",
        "pair": f"{base} vs {cand}",
        "runs": runs,
        "regression_counts": counts,
        "consistent": len(set(counts)) == 1,
        "latency_ms": {"p50": statistics.median(latencies), "max": max(latencies)},
    }


def measure_golden_status(runs: int) -> dict:
    path = ROOT / "tests" / "golden_set_status.json"
    if not path.exists():
        return {"component": "Golden CI status", "skipped": "no status file"}
    latencies = []
    scores = []
    for _ in range(runs):
        t0 = time.perf_counter()
        data = json.loads(path.read_text(encoding="utf-8"))
        latencies.append((time.perf_counter() - t0) * 1000)
        scores.append(data.get("score"))
    return {
        "component": "Golden CI status read",
        "runs": runs,
        "scores": scores,
        "consistent": len(set(scores)) == 1,
        "latency_ms": {"p50": statistics.median(latencies), "max": max(latencies)},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", default=DEFAULT_JOB)
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "job_id": args.job_id,
        "measurements": [
            measure_health(args.job_id, args.runs),
            measure_compare(args.runs),
            measure_golden_status(args.runs),
        ],
    }
    out_path = ROOT / "eval_results" / "slo_harness_latest.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
