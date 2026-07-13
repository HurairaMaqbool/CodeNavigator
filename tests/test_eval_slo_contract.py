# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Eval module SLO contract tests — deterministic, no Groq required."""
from __future__ import annotations

import json
import time
from pathlib import Path

from eval.compare_runs import compare, compare_eval_runs, load_history


def test_compare_same_run_is_deterministic_5x():
    records = load_history()
    assert records, "eval history required"
    version = records[0].get("version")
    results = []
    for _ in range(5):
        out = compare_eval_runs(version, version, tolerance=0.05)
        results.append(
            (
                out["regressions_found"],
                len(out["regressions"]),
                out["overall_pass"],
            )
        )
    assert len(set(results)) == 1, f"non-deterministic compare: {results}"


def test_compare_incomparable_question_count_is_stable_5x():
    baseline = {
        "ragas_scores": {"faithfulness": 0.9, "answer_relevancy": 0.9,
                         "context_precision": 0.9, "context_recall": 0.9},
        "diagnostics": {"question_count": 3},
    }
    candidate = {
        "ragas_scores": {"faithfulness": 0.5, "answer_relevancy": 0.5,
                         "context_precision": 0.5, "context_recall": 0.5},
        "diagnostics": {"question_count": 15},
    }
    flags = []
    for _ in range(5):
        out = compare(baseline, candidate)
        flags.append((out.get("incomparable"), out.get("regressions_found"), len(out["regressions"])))
    assert flags == [(True, False, 0)] * 5


def test_f200e26_vs_b752c76_regression_count_stable():
    """Golden compare pair from production history — must stay at 7 regressions."""
    hist_path = Path("tests/eval_results.json")
    if not hist_path.exists():
        return
    versions = {r.get("version") for r in json.loads(hist_path.read_text())}
    if "f200e26" not in versions or "b752c76" not in versions:
        return
    counts = []
    for _ in range(5):
        out = compare_eval_runs("f200e26", "b752c76", tolerance=0.05)
        counts.append(len(out.get("regressions") or []))
    assert counts == [7] * 5, f"regression count drift: {counts}"


def test_eval_precheck_latency_budget_cold():
    """Health precheck (no agent probe) should complete under 5s locally."""
    from eval.health_check import run_full_eval_precheck

    job = "375c63667dff3e1e20ef5712cf1c0cb33940a9b49644bb855f1f89fe959d9f4d"
    t0 = time.perf_counter()
    run_full_eval_precheck(job, include_agent_probe=False)
    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0, f"precheck too slow: {elapsed:.2f}s"
