# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Module #29 — eval/compare_runs.py tests."""
from __future__ import annotations


import pytest

from eval.compare_runs import (
    DEFAULT_TOLERANCE,
    MalformedReportError,
    compare,
    compare_with_baseline_file,
    load_report_file,
)


def _report(
    *,
    faithfulness: float = 0.9,
    state_rate: float = 1.0,
    state_failures: list | None = None,
    gated_flips: list | None = None,
) -> dict:
    return {
        "version": "v1",
        "ragas_scores": {
            "faithfulness": faithfulness,
            "answer_relevancy": 0.85,
            "context_precision": 0.8,
            "context_recall": 0.75,
        },
        "state_path_consistency": {
            "passed": 3 if state_rate >= 1.0 else 2,
            "total": 3,
            "rate": state_rate,
            "failures": state_failures or [],
        },
        "regression_flags": {
            "gated_flips": gated_flips or [],
            "state_path_failures": state_failures or [],
        },
    }


def test_compare_contract_shape():
    out = compare(_report(), _report())
    assert set(out.keys()) >= {"regressions", "overall_pass", "first_run_baseline_established"}
    assert out["overall_pass"] is True
    assert out["regressions"] == []


def test_first_run_no_baseline():
    out = compare(None, _report())
    assert out["overall_pass"] is True
    assert out["regressions"] == []
    assert out["first_run_baseline_established"] is True


def test_ragas_tolerance_regression():
    base = _report(faithfulness=0.90)
    new = _report(faithfulness=0.80)
    out = compare(base, new, tolerance=0.05)
    assert out["overall_pass"] is False
    reg = out["regressions"][0]
    assert reg["metric"] == "faithfulness"
    assert reg["kind"] == "tolerance_exceeded"
    assert reg["baseline_value"] == 0.90
    assert reg["new_value"] == 0.80


def test_state_path_hard_fail_no_tolerance():
    base = _report(state_rate=1.0)
    new = _report(state_rate=0.67, state_failures=[{"question": "q1"}])
    out = compare(base, new, tolerance=1.0)  # high tolerance cannot mask state-path
    assert out["overall_pass"] is False
    kinds = [r["kind"] for r in out["regressions"]]
    assert "state_path_hard_fail" in kinds


def test_gated_flip_hard_fail():
    out = compare(_report(), _report(gated_flips=[{"question": "q", "type": "gated_flip"}]))
    assert out["overall_pass"] is False
    assert any(r["kind"] == "gated_hard_fail" for r in out["regressions"])


def test_compare_with_baseline_file_first_run(tmp_path):
    path = tmp_path / "baseline.json"
    report = _report()
    out = compare_with_baseline_file(report, baseline_path=path)
    assert out["first_run_baseline_established"] is True
    assert path.exists()


def test_malformed_report_raises(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    with pytest.raises(MalformedReportError):
        load_report_file(bad)


def test_default_tolerance_value():
    assert DEFAULT_TOLERANCE == 0.05
