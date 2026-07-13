# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""P0 regression — VERIFY must gate placeholder/missing citations; RESPOND once."""
from __future__ import annotations

from unittest.mock import MagicMock, patch


from app.agent.confidence import (
    BASE_CONFIDENCE_SCORE,
    GATED_FALLBACK_MESSAGE,
    check_file_existence,
    check_line_bounds,
    evaluate,
    parse_citations,
    validate_sources,
)
from app.agent.loop import AgentState, run
from app.config import settings


PLACEHOLDER_ANSWER = (
    "Parameters are validated in `path/to/file.py:10`, `path/to/file.py:45`, "
    "`path/to/file.py:120`, `path/to/file.py:143`, and `path/to/file.py:156`."
)

MISSING_LINES_ANSWER = (
    "See `src/requests/utils.py` · `_validate_header_part` · L— for validation details."
)


def test_placeholder_citation_is_gated():
    cites = parse_citations(PLACEHOLDER_ANSWER)
    assert len(cites) >= 5
    assert all("path/to/file.py" in c["file_path"] for c in cites)

    with patch("app.agent.confidence.metadata_store") as mock_store, patch(
        "app.agent.confidence._indexed_paths_for_repo", return_value={"src/requests/utils.py"},
    ), patch("app.agent.confidence.check_graph_consistency", return_value=True), patch(
        "app.agent.confidence.check_line_bounds", return_value=True,
    ):
        mock_store.get.return_value = MagicMock(sync_status="synced")
        out = evaluate(PLACEHOLDER_ANSWER, "repo1")

    assert out["gated"] is True
    assert out["answer"] == GATED_FALLBACK_MESSAGE
    assert "path/to/file.py" not in out["answer"]
    assert out["confidence_score"] < settings.MIN_CONFIDENCE_SCORE


def test_missing_line_range_is_gated():
    cites = parse_citations(MISSING_LINES_ANSWER)
    assert len(cites) >= 1
    assert cites[0].get("unparseable") is True

    cite = {
        "file_path": "src/requests/utils.py",
        "start_line": None,
        "end_line": None,
        "repo_id": "repo1",
        "unparseable": True,
    }
    assert check_line_bounds(cite) is False

    with patch("app.agent.confidence.parse_citations", return_value=[cite]):
        out = evaluate(MISSING_LINES_ANSWER, "repo1")

    assert out["gated"] is True
    assert out["answer"] == GATED_FALLBACK_MESSAGE


def test_unparseable_citation_fails_closed():
    weird = "Mystery ref <<<not-a-real-citation-format>>>"
    cites = parse_citations(weird)
    assert cites == []

    with patch("app.agent.confidence.parse_citations", return_value=[{
        "file_path": "src/mystery.py",
        "start_line": None,
        "end_line": None,
        "function_name": None,
        "unparseable": True,
    }]):
        out = evaluate(weird, "repo1")

    assert out["gated"] is True
    assert out["confidence_score"] < BASE_CONFIDENCE_SCORE


def test_score_math_matches_penalty_rules():
    failing = [
        {
            "file_path": "path/to/file.py",
            "start_line": 10 + i,
            "end_line": 10 + i,
            "function_name": None,
            "unparseable": False,
        }
        for i in range(5)
    ]
    with patch("app.agent.confidence.parse_citations", return_value=failing), patch(
        "app.agent.confidence.check_file_existence", return_value=False,
    ), patch("app.agent.confidence.check_line_bounds", return_value=True), patch(
        "app.agent.confidence.check_graph_consistency", return_value=True,
    ):
        out = evaluate(PLACEHOLDER_ANSWER, "repo1")

    assert out["confidence_score"] <= 1.0
    assert out["gated"] is True


def test_check_file_existence_rejects_placeholder_path():
    assert check_file_existence({
        "file_path": "path/to/file.py",
        "repo_id": "repo1",
        "unparseable": False,
    }) is False


def test_validate_sources_drops_missing_line_ranges():
    sources = [{
        "file_path": "src/requests/utils.py",
        "function_name": "_validate_header_part",
        "start_line": 0,
        "end_line": 0,
    }]
    with patch("app.agent.confidence.check_file_existence", return_value=True), patch(
        "app.agent.confidence.check_line_bounds", return_value=False,
    ):
        filtered = validate_sources(sources, "repo1")
    assert filtered == []


def test_respond_fires_exactly_once():
    synced = MagicMock(sync_status="synced")
    hits = [{
        "chunk": "def validate(): pass",
        "chunk_metadata": {
            "display_path": "src/requests/utils.py",
            "file_path": "src/requests/utils.py",
            "function_name": "validate",
            "start_line": 10,
            "end_line": 20,
        },
        "score": 0.1,
    }]
    with patch("app.agent.loop.semantic_cache_lookup", return_value=None), patch(
        "app.ingestion.repo_readiness.evaluate_chat_readiness",
    ) as mock_ready, patch(
        "app.agent.loop._groq_text", side_effect=["YES", PLACEHOLDER_ANSWER],
    ), patch("app.retrieval.query_expansion.expand_query", return_value=["q"]), patch(
        "app.retrieval.hybrid_search.search", return_value=hits,
    ), patch("app.retrieval.reranker.rerank", return_value=hits), patch(
        "app.agent.loop.semantic_cache_store",
    ), patch("app.agent.confidence.metadata_store") as mock_meta, patch(
        "app.agent.confidence._indexed_paths_for_repo", return_value={"src/requests/utils.py"},
    ):
        from app.ingestion.repo_readiness import RepoReadiness

        mock_ready.return_value = RepoReadiness(
            ready=True,
            job_id="repo1",
            asset_repo_id="repo1",
            meta=synced,
        )
        mock_meta.get.return_value = synced
        out = run("repo1", "How are params validated?", job_id="repo1")

    trace_states = [t["state"] for t in out.get("trace", [])]
    assert trace_states.count(AgentState.RESPOND.value) == 1
    assert out["gated"] is True
