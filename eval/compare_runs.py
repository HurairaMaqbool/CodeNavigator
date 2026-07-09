# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
eval/compare_runs.py
--------------------
Compare two evaluation runs by version id.

History is loaded via eval.eval_store (tests/eval_results.json + jsonl fallback).
"""
from __future__ import annotations

import json

from eval.eval_store import load_runs


def load_history() -> list[dict]:
    """Return evaluation records, newest first."""
    return load_runs(newest_first=True)


def compare_eval_runs(baseline_version: str, candidate_version: str, tolerance: float = 0.05) -> dict:
    records = load_history()

    baseline = None
    candidate = None

    for r in records:
        if r.get("version") == baseline_version:
            baseline = r
        if r.get("version") == candidate_version:
            candidate = r

    if not baseline:
        raise ValueError(f"Baseline version '{baseline_version}' not found in history.")
    if not candidate:
        raise ValueError(f"Candidate version '{candidate_version}' not found in history.")

    regressions_list: list[dict] = []
    regressions_found = False

    def add_comparison(metric_name: str, base_val: float, cand_val: float, lower_is_better: bool = False):
        nonlocal regressions_found
        delta = cand_val - base_val

        status = "neutral"
        if lower_is_better:
            if delta > tolerance:
                status = "regression"
                regressions_found = True
            elif delta < -tolerance:
                status = "improvement"
        else:
            if delta < -tolerance:
                status = "regression"
                regressions_found = True
            elif delta > tolerance:
                status = "improvement"

        if status == "regression":
            regressions_list.append({
                "metric": metric_name,
                "baseline": base_val,
                "candidate": cand_val,
                "delta": delta,
                "status": status,
            })

    ragas_metrics = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]
    for m in ragas_metrics:
        base_val = baseline.get("ragas_scores", {}).get(m, 0.0)
        cand_val = candidate.get("ragas_scores", {}).get(m, 0.0)
        add_comparison(m, base_val, cand_val, lower_is_better=False)

    add_comparison(
        "mean_confidence_score",
        baseline.get("mean_confidence_score", 0.0),
        candidate.get("mean_confidence_score", 0.0),
        lower_is_better=False,
    )
    add_comparison(
        "retrieval_precision_at_3",
        baseline.get("retrieval_precision_at_3", 0.0),
        candidate.get("retrieval_precision_at_3", 0.0),
        lower_is_better=False,
    )
    add_comparison(
        "invalid_reference_rate",
        baseline.get("invalid_reference_rate", 0.0),
        candidate.get("invalid_reference_rate", 0.0),
        lower_is_better=True,
    )
    add_comparison(
        "average_iterations",
        baseline.get("average_iterations", 0.0),
        candidate.get("average_iterations", 0.0),
        lower_is_better=True,
    )

    return {
        "baseline_version": baseline_version,
        "candidate_version": candidate_version,
        "regressions_found": regressions_found,
        "regressions": regressions_list,
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python compare_runs.py <baseline_version> <candidate_version>")
        sys.exit(1)
    print(json.dumps(compare_eval_runs(sys.argv[1], sys.argv[2]), indent=2))
