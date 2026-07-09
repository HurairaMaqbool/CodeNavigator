"""Module #22 — tools.py validation and dispatch verification."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.agent.tools import (
    ToolValidationError,
    execute,
    execute_tool_with_retry,
    validate_call,
)


def test_validate_unknown_tool():
    with pytest.raises(ToolValidationError, match="Unknown tool"):
        validate_call("no_such_tool", {})


def test_validate_search_code_missing_query():
    with pytest.raises(ToolValidationError):
        validate_call("search_code", {"top_k": 5})


def test_validate_search_code_ok():
    call = validate_call("search_code", {"query": "login flow"})
    assert call.tool_name == "search_code"
    assert call.arguments["query"] == "login flow"
    assert call.arguments["top_k"] == 5


def test_execute_unknown_tool_structured_error():
    out = execute("missing_tool", {}, "repo-1")
    assert out["success"] is False
    assert out["error"]
    assert out["result"] is None


def test_execute_invalid_schema_structured_error():
    out = execute("read_file", {}, "repo-1")
    assert out["success"] is False
    assert "Schema validation" in out["error"] or "validation" in out["error"].lower()


def test_search_code_search_then_rerank_order():
    search_hits = [{"chunk": "x", "chunk_metadata": {"file_path": "a.py"}, "score": 0.5}]
    reranked = [{"chunk": "x", "chunk_metadata": {"file_path": "a.py"}, "score": 0.9}]
    call_order: list[str] = []

    def fake_search(*_a, **_k):
        call_order.append("search")
        return search_hits

    def fake_rerank(*_a, **_k):
        call_order.append("rerank")
        return reranked

    with patch("app.retrieval.hybrid_search.search", side_effect=fake_search), patch(
        "app.retrieval.reranker.rerank", side_effect=fake_rerank
    ):
        out = execute("search_code", {"query": "auth"}, "repo-1")

    assert out["success"] is True
    assert call_order == ["search", "rerank"]
    assert out["result"]["results"][0]["rerank_score"] == 0.9


def test_generate_diagram_subgraph_then_mermaid():
    with patch("app.graph.queries.get_subgraph") as mock_sub, patch(
        "app.diagrams.mermaid_generator.generate_mermaid", return_value="graph TD\n  a"
    ) as mock_mermaid:
        mock_sub.return_value = {"nodes": [], "edges": [], "clamped": False}
        out = execute("generate_diagram", {"name": "main", "depth": 2}, "repo-1")

    assert out["success"] is True
    mock_sub.assert_called_once()
    mock_mermaid.assert_called_once()
    assert out["result"]["mermaid"].startswith("graph")


def test_read_file_path_jail_error_structured():
    with patch("app.agent.tools._do_read_file", return_value={"error": "Path escapes jail"}):
        out = execute("read_file", {"file_path": "../../etc/passwd"}, "repo-1")
    assert out["success"] is False
    assert "Path" in out["error"]


def test_transient_io_retries_then_structured():
    calls = {"n": 0}

    def flaky_read(*_a, **_k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("temp io")
        return {"content": "ok"}

    with patch("app.agent.tools._do_read_file", side_effect=flaky_read), patch(
        "app.agent.tools.time.sleep"
    ):
        out = execute("read_file", {"file_path": "f.py"}, "repo", max_retries=2)

    assert calls["n"] == 2
    assert out["success"] is True


def test_execute_tool_with_retry_legacy_retry():
    calls = {"n": 0}

    def boom(*_a, **_k):
        calls["n"] += 1
        raise RuntimeError("transient")

    with patch("app.agent.tools._do_search_code", side_effect=boom), patch("app.agent.tools.time.sleep"):
        res = execute_tool_with_retry("search_code", {"query": "x"}, "repo")

    assert calls["n"] == 2
    assert "error" in res
