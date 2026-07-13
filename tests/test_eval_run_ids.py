# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Regression tests for eval run id uniqueness and compare lookup."""
from __future__ import annotations

from eval.compare_runs import compare_eval_runs
from eval.eval_store import _normalize_runs, append_run, load_runs


def test_normalize_runs_assigns_unique_ids_for_duplicate_versions():
    raw = [
        {"version": "b752c76", "timestamp": "2026-07-11T15:01:25+00:00"},
        {"version": "b752c76", "timestamp": "2026-07-11T15:18:24+00:00"},
        {"version": "b752c76", "timestamp": "2026-07-11T15:28:44+00:00"},
    ]
    normalized = _normalize_runs(raw)
    ids = [r["run_id"] for r in normalized]
    assert len(ids) == len(set(ids))
    assert all("b752c76::" in rid for rid in ids)


def test_append_run_assigns_run_id(tmp_path, monkeypatch):
    monkeypatch.setattr("eval.eval_store.HISTORY_JSON", tmp_path / "eval_results.json")
    monkeypatch.setattr("eval.eval_store.HISTORY_JSONL", tmp_path / "eval_history.jsonl")
    record = {"version": "test_v1", "timestamp": "2026-01-01T00:00:00+00:00"}
    saved = append_run(record)
    assert saved.get("run_id")
    loaded = load_runs()
    assert len(loaded) == 1
    assert loaded[0]["run_id"] == saved["run_id"]


def test_compare_eval_runs_resolves_by_run_id():
    runs = _normalize_runs([
        {
            "version": "dup",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "ragas_scores": {"faithfulness": 0.9},
        },
        {
            "version": "dup",
            "timestamp": "2026-01-02T00:00:00+00:00",
            "ragas_scores": {"faithfulness": 0.5},
        },
    ])
    baseline_id = runs[0]["run_id"]
    candidate_id = runs[1]["run_id"]

    import eval.compare_runs as compare_mod

    original = compare_mod.load_history
    compare_mod.load_history = lambda: runs
    try:
        result = compare_eval_runs(baseline_id, candidate_id, tolerance=0.05)
    finally:
        compare_mod.load_history = original

    assert result["baseline_version"] == baseline_id
    assert result["candidate_version"] == candidate_id
    assert result["regressions_found"] is True
