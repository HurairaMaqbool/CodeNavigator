# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""Regression tests for diagram alias, cycle detection, and eval imports."""
from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.auth import verify_api_key
from app.api.router import _resolve_repo_meta
from app.graph.queries import _GRAPH_CACHE, detect_cycles, get_subgraph
from app.main import app

JOB_ID = "375c63667dff3e1e20ef5712cf1c0cb33940a9b49644bb855f1f89fe959d9f4d"
CLONE_ID = "b4f947369301e4e0681a5f878604aa39c14efce4fbd98648e3722afd9f6380ee"
ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def requests_fixture_paths():
    alias = ROOT / "data" / "repos" / JOB_ID / "alias.json"
    graph = ROOT / "data" / "graph_store" / CLONE_ID / "graph.json"
    if not alias.exists() or not graph.exists():
        pytest.skip("requests ingest fixture missing — run ingest once to populate data/")
    return alias, graph


def _make_fake_git_tree(root: Path) -> Path:
    """Create a tree containing a read-only .git packfile, mimicking a clone."""
    src = root / "src"
    pack = src / ".git" / "objects" / "pack"
    pack.mkdir(parents=True)
    idx = pack / "pack-deadbeef.idx"
    idx.write_bytes(b"x" * 64)
    os.chmod(idx, stat.S_IREAD)  # git marks pack files read-only
    (src / "main.py").write_text("print('hi')\n")
    return src


def test_force_remove_tree_deletes_readonly_git_files():
    """force_remove_tree must clear read-only attrs (the WinError 5 cause)."""
    from app.ingestion.clone import force_remove_tree

    base = Path(tempfile.mkdtemp())
    try:
        src = _make_fake_git_tree(base)
        force_remove_tree(src)
        assert not src.exists()
    finally:
        force_remove_tree(base, ignore_errors=True)


def test_safe_move_tree_preserves_readonly_children():
    """_safe_move_tree must not raise on read-only children (shutil.move bug)."""
    from app.ingestion.clone import _safe_move_tree, force_remove_tree

    base = Path(tempfile.mkdtemp())
    try:
        src = _make_fake_git_tree(base)
        dst = base / "final"
        _safe_move_tree(src, dst)
        assert not src.exists()
        assert (dst / "main.py").exists()
        assert (dst / ".git" / "objects" / "pack" / "pack-deadbeef.idx").exists()
    finally:
        force_remove_tree(base, ignore_errors=True)


def test_response_firewall_strips_leaks():
    from app.agent.response_firewall import sanitize_user_answer, has_forbidden_leak

    dirty = (
        "I will try a different query.\n"
        '<function=search_code>{"query": "auth", "top_k": 2}</function>\n'
        "Tool call budget exhausted. You can use read_file.\n"
        "HTTPBasicAuth is in `src/requests/auth.py:76`."
    )
    clean = sanitize_user_answer(dirty)
    assert "<function=" not in clean
    assert "budget exhausted" not in clean.lower()
    assert "read_file" not in clean.lower()
    assert "auth.py:76" in clean
    assert not has_forbidden_leak(clean)


def test_eval_dependencies_importable():
    import datasets  # noqa: F401
    try:
        import ragas  # noqa: F401
    except ModuleNotFoundError as exc:
        if "vertexai" in str(exc):
            pytest.skip("ragas needs langchain-community 0.3.x — pip install -r requirements-eval.txt")
        raise


def test_resolve_repo_meta_follows_alias(requests_fixture_paths):
    _, _ = requests_fixture_paths
    meta, asset_id = _resolve_repo_meta(JOB_ID)
    assert meta is not None
    assert asset_id == CLONE_ID


def test_prepared_request_subgraph_via_alias(requests_fixture_paths):
    _, _ = requests_fixture_paths
    _GRAPH_CACHE.clear()
    sub = get_subgraph(CLONE_ID, "PreparedRequest", depth=2)
    assert len(sub["nodes"]) > 0
    assert len(sub["edges"]) > 0


def test_diagram_endpoint_uses_job_id(requests_fixture_paths):
    _, _ = requests_fixture_paths
    _GRAPH_CACHE.clear()
    app.dependency_overrides[verify_api_key] = lambda: None
    client = TestClient(app)
    resp = client.get(f"/diagram/{JOB_ID}/PreparedRequest?depth=2")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("empty") is not True
    assert body.get("mermaid")


def test_detect_cycles_on_requests_graph(requests_fixture_paths):
    _, _ = requests_fixture_paths
    _GRAPH_CACHE.clear()
    assert detect_cycles(CLONE_ID) is not None


def test_status_cycle_field_from_detect_cycles(requests_fixture_paths):
    _, graph_path = requests_fixture_paths
    app.dependency_overrides[verify_api_key] = lambda: None
    client = TestClient(app)
    payload = json.loads(graph_path.read_text(encoding="utf-8"))
    # Old graphs may lack the field; endpoint should compute it.
    payload["metadata"].pop("has_circular_dependencies", None)
    with patch("pathlib.Path.exists", return_value=True), patch(
        "pathlib.Path.read_text", return_value=json.dumps(payload)
    ), patch("app.api.router.metadata_store") as mock_meta:
        mock_meta.get.return_value = MagicMock(
            sync_status="synced",
            commit_hash="abc",
            ref="main",
            error_reason=None,
            org_id="default",
        )
        mock_meta.get_alias.return_value = CLONE_ID
        with patch("app.graph.queries.detect_cycles", return_value=True):
            resp = client.get(f"/status/{JOB_ID}")
    assert resp.status_code == 200
    assert resp.json()["has_circular_dependencies"] is True


def test_eval_resolve_asset_repo_id_matches_chat_api(requests_fixture_paths):
    _, _ = requests_fixture_paths
    from eval.health_check import resolve_asset_repo_id

    _, asset_id = resolve_asset_repo_id(JOB_ID)
    assert asset_id == CLONE_ID


def test_compare_runs_reads_eval_results_json():
    from eval.compare_runs import load_history, compare_eval_runs

    records = load_history()
    assert records, "eval_results.json should contain runs"
    v = records[0].get("version")
    assert v
    diff = compare_eval_runs(v, v, tolerance=0.05)
    assert diff["baseline_version"] == v
    assert diff["candidate_version"] == v
    assert diff["regressions_found"] is False


def test_eval_context_builder_uses_retrieval_chunks():
    from eval.context_builder import build_ragas_contexts

    res = {
        "trace": [],
        "sources": [{"file_path": "src/requests/models.py", "function_name": "PreparedRequest"}],
        "retrieval_hits": [
            {
                "file_path": "src/requests/models.py",
                "function_name": "PreparedRequest",
                "start_line": 10,
                "end_line": 40,
                "chunk": "class PreparedRequest:\n    '''Represents a fully prepared HTTP request.'''",
            }
        ],
    }
    ctx, sentinel = build_ragas_contexts(res)
    assert not sentinel
    assert len(ctx) == 1
    assert "PreparedRequest" in ctx[0]
    assert "fully prepared HTTP request" in ctx[0]


def test_citation_repair_strips_ungrounded_and_fixes_lines():
    from app.agent.citation_repair import repair_answer_citations, enforce_word_limit

    hits = [
        {
            "file_path": "src/requests/sessions.py",
            "function_name": "Session.__init__",
            "start_line": 442,
            "end_line": 460,
            "rerank_score": 0.9,
            "chunk": "class Session",
        },
        {
            "file_path": "src/requests/api.py",
            "function_name": "get",
            "start_line": 74,
            "end_line": 90,
            "rerank_score": 0.85,
            "chunk": "def get(",
        },
    ]
    verbose = (
        "The Session class persists cookies. `Session` is in `src/requests/sessions.py:655`. "
        "`requests.get()` is in `src/requests/api.py:21`. "
        "Unrelated: `HTTPBasicAuth` in `src/requests/auth.py:76`. "
        "In summary, both are useful."
    )
    repo_id = CLONE_ID if (ROOT / "data" / "repos" / CLONE_ID).exists() else None
    repaired = repair_answer_citations(verbose, hits, repo_id=repo_id)
    assert "auth.py" not in repaired
    assert "In summary" not in repaired
    assert "sessions.py:395" in repaired or "sessions.py:442" in repaired or "api.py:74" in repaired
    assert len(enforce_word_limit(" ".join(["word"] * 150), 120).split()) <= 121


def test_symbol_lookup_session_class_line(requests_fixture_paths):
    from app.agent.symbol_lookup import resolve_symbol_location

    loc = resolve_symbol_location(CLONE_ID, "Session", prefer_path="src/requests/sessions.py", kind="class")
    assert loc is not None
    assert loc["start_line"] == 395
    assert "sessions.py" in loc["file_path"]


def test_eval_regression_only_compares_same_question_count():
    from eval.run_eval import _find_comparable_baseline, _check_regressions

    prior = [
        {"version": "v3", "diagnostics": {"question_count": 3}, "ragas_scores": {"faithfulness": 0.8}},
        {"version": "v10-old", "diagnostics": {"question_count": 10}, "ragas_scores": {"faithfulness": 0.7}},
    ]
    baseline = _find_comparable_baseline(prior, 10)
    assert baseline["version"] == "v10-old"
    assert _find_comparable_baseline(prior, 3)["version"] == "v3"

    # No false regression when comparing 10-Q to 3-Q baseline
    assert _find_comparable_baseline([prior[0]], 10) is None

    regs = _check_regressions(
        {"faithfulness": 0.8, "answer_relevancy": 0.9},
        {"faithfulness": 0.65, "answer_relevancy": 0.78},
    )
    assert any("faithfulness" in r for r in regs)


def test_eval_pipeline_failure_detects_all_zero_ragas():
    from eval.health_check import diagnose_pipeline_failure

    scores = {
        "faithfulness": 0.0,
        "answer_relevancy": 0.0,
        "context_precision": 0.0,
        "context_recall": 0.0,
    }
    is_fail, reason = diagnose_pipeline_failure(
        scores,
        question_count=10,
        gated_count=9,
        empty_source_count=10,
        sentinel_context_count=10,
        retrieval_precision_at_3=0.0,
        mean_confidence=3.0,
    )
    assert is_fail
    assert "gated" in reason.lower() or "empty" in reason.lower()
