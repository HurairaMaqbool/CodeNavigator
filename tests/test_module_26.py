# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Module #26 — confidence VERIFY guard tests."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.agent.confidence import (
    BASE_CONFIDENCE_SCORE,
    GATED_FALLBACK_MESSAGE,
    PENALTY_FILE_EXISTENCE,
    check_file_existence,
    check_graph_consistency,
    check_line_bounds,
    evaluate,
    parse_citations,
)
from app.config import settings


def test_parse_citations_matches_finalize_format():
    text = "See `validate_token()` in `src/auth/login.py:12-14` for details."
    cites = parse_citations(text)
    assert len(cites) == 1
    assert cites[0]["file_path"] == "src/auth/login.py"
    assert cites[0]["start_line"] == 12
    assert cites[0]["end_line"] == 14
    assert cites[0]["function_name"] == "validate_token"
    assert cites[0]["unparseable"] is False


def test_parse_citations_flags_unparseable_fail_closed():
    cites = parse_citations("Broken cite `src/auth/login.py` without lines.")
    assert len(cites) == 1
    assert cites[0]["unparseable"] is True


def test_evaluate_output_contract():
    with patch("app.agent.confidence.parse_citations", return_value=[]):
        out = evaluate("No cites here.", "repo1")
    assert set(out.keys()) == {"answer", "confidence_score", "gated"}
    assert out["answer"] == "No cites here."
    assert out["confidence_score"] == BASE_CONFIDENCE_SCORE
    assert out["gated"] is False


def test_evaluate_gates_and_replaces_answer():
    bad_cite = {
        "file_path": "fake.py",
        "start_line": 1,
        "end_line": 2,
        "function_name": "missing",
        "unparseable": False,
        "repo_id": "repo1",
    }
    with patch("app.agent.confidence.parse_citations", return_value=[bad_cite]), patch(
        "app.agent.confidence.check_file_existence", return_value=False
    ), patch("app.agent.confidence.check_line_bounds", return_value=False), patch(
        "app.agent.confidence.check_graph_consistency", return_value=False
    ):
        out = evaluate("RAW `fake.py:1-2`", "repo1")

    assert out["gated"] is True
    assert out["answer"] == GATED_FALLBACK_MESSAGE
    assert "RAW" not in out["answer"]
    assert out["confidence_score"] < settings.MIN_CONFIDENCE_SCORE


def test_evaluate_unparseable_applies_file_penalty_only():
    unparseable = {
        "file_path": "src/x.py",
        "start_line": None,
        "end_line": None,
        "function_name": None,
        "unparseable": True,
    }
    with patch("app.agent.confidence.parse_citations", return_value=[unparseable]):
        out = evaluate("bad `src/x.py`", "repo1")
    expected = max(0.0, BASE_CONFIDENCE_SCORE - PENALTY_FILE_EXISTENCE)
    assert out["confidence_score"] == expected


def test_check_file_existence_uses_metadata_store_and_index(tmp_path):
    repo_id = "repo1"
    meta = MagicMock(sync_status="synced")
    with patch("app.agent.confidence.metadata_store") as mock_store, patch(
        "app.agent.confidence._indexed_paths_for_repo", return_value={"src/a.py"}
    ):
        mock_store.get.return_value = meta
        ok = check_file_existence({
            "file_path": "src/a.py",
            "repo_id": repo_id,
            "unparseable": False,
        })
    assert ok is True


def test_check_line_bounds_reads_clone_file(tmp_path):
    repo_id = "repo1"
    clone = tmp_path / repo_id / "clone" / "src"
    clone.mkdir(parents=True)
    (clone / "a.py").write_text("line1\nline2\nline3\n", encoding="utf-8")

    with patch.object(settings, "REPOS_PATH", str(tmp_path)):
        ok = check_line_bounds({
            "file_path": "src/a.py",
            "start_line": 1,
            "end_line": 3,
            "repo_id": repo_id,
            "unparseable": False,
        })
    assert ok is True


def test_check_graph_consistency_uses_builder_graph():
    import networkx as nx

    graph = nx.DiGraph()
    graph.add_node("src/a.py:foo", path="src/a.py", name="foo", type="function")

    with patch("app.graph.builder.get_graph", return_value=graph):
        ok = check_graph_consistency({
            "file_path": "src/a.py",
            "start_line": 1,
            "end_line": 2,
            "function_name": "foo",
            "repo_id": "repo1",
            "unparseable": False,
        })
    assert ok is True


def test_evaluate_never_raises_on_malformed_input():
    with patch("app.agent.confidence.parse_citations", side_effect=ValueError("boom")):
        out = evaluate(None, "repo1")  # type: ignore[arg-type]
    assert out["gated"] is True
    assert out["answer"] == GATED_FALLBACK_MESSAGE
