# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
eval/compare_runs.py
--------------------
Module #29 — Regression detection across eval reports.

Pure JSON diffing — zero LLM/Groq calls. Reads Module #28 report schema from
``eval/run_eval.py`` and emits a deploy gate ``{regressions, overall_pass}``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eval.eval_store import load_runs

# Absolute score drop allowed for RAGAS metrics (0–1 scale). Default 0.05 = five points.
DEFAULT_TOLERANCE: float = 0.05

RAGAS_METRICS: tuple[str, ...] = (
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
)

SECONDARY_METRICS: tuple[tuple[str, bool], ...] = (
    ("mean_confidence_score", False),
    ("retrieval_precision_at_3", False),
    ("invalid_reference_rate", True),
    ("average_iterations", True),
)

# Optional persisted baseline for file-based first-run workflow.
BASELINE_REPORT_PATH = Path("tests/eval_baseline.json")


class MalformedReportError(ValueError):
    """Raised when an eval report file cannot be parsed or is not a JSON object."""


def load_history() -> list[dict[str, Any]]:
    """Return evaluation records, newest first (backward-compatible alias)."""
    return load_runs(newest_first=True)


def load_report_file(path: str | Path) -> dict[str, Any]:
    """Load a Module #28 JSON report from disk; raise on missing or malformed input."""
    report_path = Path(path)
    if not report_path.exists():
        raise FileNotFoundError(f"Eval report not found: {report_path}")
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MalformedReportError(f"Malformed eval report JSON: {report_path}") from exc
    if not isinstance(data, dict):
        raise MalformedReportError(f"Eval report must be a JSON object: {report_path}")
    return data


def _ragas_scores(report: dict[str, Any]) -> dict[str, float]:
    """Read RAGAS means from Module #28 top-level or ``aggregate.ragas_scores``."""
    raw = report.get("ragas_scores")
    if not raw:
        raw = (report.get("aggregate") or {}).get("ragas_scores") or {}
    return {m: float(raw.get(m, 0.0)) for m in RAGAS_METRICS}


def _state_path_rate(report: dict[str, Any]) -> float:
    """Read ``state_path_consistency.rate`` (Module #28); 1.0 when absent (legacy)."""
    sp = report.get("state_path_consistency") or {}
    if "rate" in sp:
        return float(sp["rate"])
    passed = int(sp.get("passed", 0))
    total = int(sp.get("total", 0))
    if total > 0:
        return passed / total
    agg = report.get("aggregate") or {}
    if "state_path_consistency_rate" in agg:
        return float(agg["state_path_consistency_rate"])
    return 1.0


def _state_path_failures(report: dict[str, Any]) -> list[dict[str, Any]]:
    sp = report.get("state_path_consistency") or {}
    failures = sp.get("failures")
    if isinstance(failures, list):
        return failures
    flags = report.get("regression_flags") or {}
    spf = flags.get("state_path_failures")
    return spf if isinstance(spf, list) else []


def _state_path_ok(report: dict[str, Any]) -> bool:
    if _state_path_failures(report):
        return False
    return _state_path_rate(report) >= 1.0


def _scalar_metric(report: dict[str, Any], key: str, default: float = 0.0) -> float:
    if key in report:
        return float(report[key])
    return float((report.get("aggregate") or {}).get(key, default))


def _append_tolerance_regression(
    regressions: list[dict[str, Any]],
    *,
    metric: str,
    baseline_value: float,
    new_value: float,
    tolerance: float,
) -> None:
    delta = new_value - baseline_value
    if delta < -tolerance:
        regressions.append({
            "metric": metric,
            "baseline_value": baseline_value,
            "new_value": new_value,
            "delta": delta,
            "kind": "tolerance_exceeded",
            "message": (
                f"{metric} dropped by {abs(delta):.4f} "
                f"(baseline={baseline_value:.4f}, new={new_value:.4f}, tolerance={tolerance})"
            ),
        })


def compare(
    baseline_report: dict[str, Any] | None,
    new_report: dict[str, Any],
    tolerance: float = DEFAULT_TOLERANCE,
) -> dict[str, Any]:
    """
    Diff two Module #28 eval reports.

    Returns::

        {
          "regressions": [
            {
              "metric": str,
              "baseline_value": float,
              "new_value": float,
              "delta": float,
              "kind": "tolerance_exceeded" | "state_path_hard_fail" | "gated_hard_fail",
              "message": str,
              ...optional details...
            }
          ],
          "overall_pass": bool,
          "first_run_baseline_established": bool,  # True only when baseline is None
        }
    """
    if not isinstance(new_report, dict):
        raise MalformedReportError("new_report must be a dict")

    if baseline_report is None:
        return {
            "regressions": [],
            "overall_pass": True,
            "first_run_baseline_established": True,
        }

    if not isinstance(baseline_report, dict):
        raise MalformedReportError("baseline_report must be a dict or None")

    if baseline_report is new_report or (
        baseline_report.get("version") and baseline_report.get("version") == new_report.get("version")
    ):
        return {
            "regressions": [],
            "overall_pass": True,
            "first_run_baseline_established": False,
        }

    regressions: list[dict[str, Any]] = []

    base_rate = _state_path_rate(baseline_report)
    new_rate = _state_path_rate(new_report)
    if not _state_path_ok(new_report) or (base_rate >= 1.0 and new_rate < 1.0):
        regressions.append({
            "metric": "state_path_consistency",
            "baseline_value": base_rate,
            "new_value": new_rate,
            "delta": new_rate - base_rate,
            "kind": "state_path_hard_fail",
            "message": (
                "State-path consistency failure — nondeterminism regression "
                "(hard fail, no tolerance applied)"
            ),
            "failures": _state_path_failures(new_report),
        })

    base_ragas = _ragas_scores(baseline_report)
    new_ragas = _ragas_scores(new_report)
    for metric in RAGAS_METRICS:
        _append_tolerance_regression(
            regressions,
            metric=metric,
            baseline_value=base_ragas[metric],
            new_value=new_ragas[metric],
            tolerance=tolerance,
        )

    for metric, lower_is_better in SECONDARY_METRICS:
        baseline_value = _scalar_metric(baseline_report, metric)
        new_value = _scalar_metric(new_report, metric)
        delta = new_value - baseline_value
        if lower_is_better:
            if delta > tolerance:
                regressions.append({
                    "metric": metric,
                    "baseline_value": baseline_value,
                    "new_value": new_value,
                    "delta": delta,
                    "kind": "tolerance_exceeded",
                    "message": (
                        f"{metric} increased by {delta:.4f} "
                        f"(baseline={baseline_value:.4f}, new={new_value:.4f}, tolerance={tolerance})"
                    ),
                })
        else:
            _append_tolerance_regression(
                regressions,
                metric=metric,
                baseline_value=baseline_value,
                new_value=new_value,
                tolerance=tolerance,
            )

    gated_flips = (new_report.get("regression_flags") or {}).get("gated_flips") or []
    if gated_flips:
        regressions.append({
            "metric": "gated_regression",
            "baseline_value": 0.0,
            "new_value": float(len(gated_flips)),
            "delta": float(len(gated_flips)),
            "kind": "gated_hard_fail",
            "message": (
                f"{len(gated_flips)} golden question(s) returned gated=true unexpectedly"
            ),
            "details": gated_flips,
        })

    return {
        "regressions": regressions,
        "overall_pass": len(regressions) == 0,
        "first_run_baseline_established": False,
    }


def compare_with_baseline_file(
    new_report: dict[str, Any],
    *,
    baseline_path: Path | None = None,
    tolerance: float = DEFAULT_TOLERANCE,
) -> dict[str, Any]:
    """
    File-based compare with first-run baseline establishment.

    When ``baseline_path`` is missing, writes ``new_report`` as the baseline and
  returns ``first_run_baseline_established=True``.
    """
    path = baseline_path or BASELINE_REPORT_PATH
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(new_report, indent=2), encoding="utf-8")
        return compare(None, new_report, tolerance)
    baseline_report = load_report_file(path)
    return compare(baseline_report, new_report, tolerance)


def compare_eval_runs(
    baseline_version: str,
    candidate_version: str,
    tolerance: float = DEFAULT_TOLERANCE,
) -> dict[str, Any]:
    """
    Version-id wrapper over eval_store history (backward-compatible API / router).

    Missing version ids raise ``ValueError`` — use ``compare(None, ...)`` or
    ``compare_with_baseline_file`` for first-run baseline semantics.
    """
    records = load_history()
    baseline = next((r for r in records if r.get("version") == baseline_version), None)
    candidate = next((r for r in records if r.get("version") == candidate_version), None)

    if not baseline:
        raise ValueError(f"Baseline version '{baseline_version}' not found in history.")
    if not candidate:
        raise ValueError(f"Candidate version '{candidate_version}' not found in history.")

    result = compare(baseline, candidate, tolerance)
    result["baseline_version"] = baseline_version
    result["candidate_version"] = candidate_version
    result["regressions_found"] = not result["overall_pass"]
    return result


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python compare_runs.py <baseline_version> <candidate_version> [tolerance]")
        sys.exit(1)
    tol = float(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_TOLERANCE
    print(json.dumps(compare_eval_runs(sys.argv[1], sys.argv[2], tolerance=tol), indent=2))
