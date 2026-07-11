# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Module #28 — eval/run_eval.py tests."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from eval.run_eval import (
    DEFAULT_GOLDEN_SET_PATH,
    _extract_state_path,
    _flag_gated_regressions,
    load_golden_set,
    state_path_consistency,
)


def test_load_golden_set_from_file(tmp_path):
    golden = [{
        "repo_id": "r1",
        "question": "What is main?",
        "ground_truth_files": ["main.py"],
        "ground_truth_answer_summary": "entrypoint",
    }]
    path = tmp_path / "golden.json"
    path.write_text(json.dumps(golden), encoding="utf-8")
    loaded = load_golden_set(path)
    assert len(loaded) == 1
    assert loaded[0]["question"] == "What is main?"


def test_extract_state_path_from_trace():
    trace = {
        "trace": [
            {"state": "INTAKE"},
            {"state": "PLAN"},
            {"state": "RESPOND"},
        ],
    }
    assert _extract_state_path(trace) == ["INTAKE", "PLAN", "RESPOND"]


def test_state_path_consistency_true():
    response = {"trace": [{"state": "INTAKE"}, {"state": "RESPOND"}]}
    with patch("eval.run_eval._invoke_chat_endpoint", return_value=response):
        assert state_path_consistency("q?", "repo1", n_runs=3) is True


def test_state_path_consistency_false():
    responses = [
        {"trace": [{"state": "INTAKE"}, {"state": "PLAN"}]},
        {"trace": [{"state": "INTAKE"}, {"state": "FINALIZE"}]},
    ]
    with patch("eval.run_eval._invoke_chat_endpoint", side_effect=responses):
        assert state_path_consistency("q?", "repo1", n_runs=2) is False


def test_gated_regression_flagged_not_averaged():
    per_q = [{"question": "q1", "gated": True}]
    cases = [{"question": "q1", "expected_gated": False}]
    flags = _flag_gated_regressions(per_q, cases)
    assert len(flags) == 1
    assert flags[0]["type"] == "gated_flip"
    assert per_q[0]["gated_regression"] is True


def test_run_golden_set_report_shape(tmp_path):
    golden = [{
        "repo_id": "job1",
        "question": "Where is auth handled?",
        "ground_truth_files": ["auth.py"],
        "ground_truth_answer_summary": "auth module",
        "expected_gated": False,
    }]
    path = tmp_path / "golden.json"
    path.write_text(json.dumps(golden), encoding="utf-8")

    chat_resp = {
        "answer": "See auth.py",
        "sources": [{"file_path": "auth.py"}],
        "confidence_score": 8.0,
        "gated": False,
        "trace": [{"state": "INTAKE"}, {"state": "RESPOND"}],
    }

    mock_health = MagicMock()
    mock_health.raise_if_failed = MagicMock()

    ragas_df = pd.DataFrame({
        "faithfulness": [0.9],
        "answer_relevancy": [0.8],
        "context_precision": [0.7],
        "context_recall": [0.75],
    })
    mock_ragas_result = MagicMock()
    mock_ragas_result.to_pandas.return_value = ragas_df

    ready = MagicMock(
        ready=True,
        asset_repo_id="asset1",
        sync_status="synced",
        files_parsed=10,
        chunks_created=100,
        meta=MagicMock(sync_status="synced"),
    )
    with patch("eval.run_eval.is_repo_ready", return_value=ready), patch(
        "eval.run_eval.check_index_health", return_value=mock_health
    ), patch("eval.run_eval.require_groq_quota"), patch(
        "eval.run_eval._invoke_chat_endpoint", return_value=chat_resp
    ), patch("eval.run_eval.build_ragas_contexts", return_value=(["ctx"], False)), patch(
        "eval.run_eval.precision_at_k", return_value=(1.0, ["auth.py"], True)
    ), patch("eval.run_eval.append_run"), patch("eval.run_eval.load_runs", return_value=[]), patch(
        "eval.run_eval.diagnose_pipeline_failure", return_value=(False, "")
    ), patch("eval.run_eval.eval_question_delay"), patch(
        "datasets.Dataset.from_dict", return_value=MagicMock()
    ), patch("ragas.evaluate", return_value=mock_ragas_result), patch(
        "eval.ragas_providers.get_judge_llm", return_value=MagicMock()
    ), patch("eval.ragas_providers.get_judge_embeddings", return_value=MagicMock()):
        from eval.run_eval import run_golden_set

        report = run_golden_set(path, target_repo_id="job1")

    assert "per_question" in report
    assert "aggregate" in report
    assert "ragas_scores" in report
    assert "regression_flags" in report
    item = report["per_question"][0]
    assert item["state_path_consistent"] is True
    assert "expected_citations" in item
    assert report["aggregate"]["ragas_scores"]["faithfulness"] == 0.9


def test_default_golden_set_path_exists():
    assert DEFAULT_GOLDEN_SET_PATH.exists() or Path("tests/eval_set.json").exists()
