"""Module #21 — agent loop state machine verification."""
from __future__ import annotations

from unittest.mock import MagicMock, patch


from app.agent.loop import (
    AgentContext,
    AgentState,
    _STATE_HANDLERS,
    confidence_verify,
    context_manager_assemble,
    run,
    semantic_cache_lookup,
)


def test_state_handlers_registered():
    for state in AgentState:
        assert state in _STATE_HANDLERS


def test_run_intake_not_synced_zero_groq():
    ctx_meta = MagicMock()
    ctx_meta.sync_status = "pending"
    with patch("app.agent.loop.semantic_cache_lookup", return_value=None), patch(
        "app.agent.loop.metadata_store.get", return_value=ctx_meta
    ), patch("app.agent.loop._groq_text") as mock_groq:
        out = run("repo-x", "How does authentication work?", None)
    mock_groq.assert_not_called()
    assert "indexing" in out["answer"].lower()
    assert out["gated"] is True


def test_run_cache_hit_skips_groq():
    cached = {
        "answer": "Cached answer.",
        "sources": [],
        "confidence_score": 8.0,
        "gated": False,
    }
    with patch("app.agent.loop.semantic_cache_lookup", return_value=cached), patch(
        "app.agent.loop._groq_text"
    ) as mock_groq:
        out = run("repo-x", "How does login work?", None)
    mock_groq.assert_not_called()
    assert out["answer"] == "Cached answer."
    assert out.get("cache_hit") is True


def test_act_chains_search_then_rerank():
    from app.agent.loop import _handle_act, _handle_plan

    ctx = AgentContext(repo_id="r1", question="Who calls authenticate?")
    _handle_plan(ctx)
    search_hits = [{"chunk": "def authenticate(): pass", "chunk_metadata": {"file_path": "a.py"}, "score": 0.5}]
    reranked = [{"chunk": "def authenticate(): pass", "chunk_metadata": {"file_path": "a.py"}, "score": 0.9}]

    with patch("app.retrieval.hybrid_search.search", return_value=search_hits) as mock_search, patch(
        "app.retrieval.reranker.rerank", return_value=reranked
    ) as mock_rerank, patch("app.graph.queries.get_callers", return_value=[]), patch(
        "app.graph.queries.get_callees", return_value=[]
    ):
        _handle_act(ctx)

    mock_search.assert_called()
    mock_rerank.assert_called_once()
    assert mock_rerank.call_args[0][0] == ctx.question
    assert ctx.chunks == reranked


def test_max_iterations_forces_finalize_gated():
    evaluate_out = {
        "confidence_score": 2.0,
        "gated": True,
        "sources": [],
        "citations": [],
        "answer": "Could not verify answer.",
    }
    with patch("app.agent.loop.semantic_cache_lookup", return_value=None), patch(
        "app.agent.loop.metadata_store.get"
    ) as mock_meta, patch(
        "app.ingestion.repo_readiness.evaluate_chat_readiness",
        return_value=MagicMock(ready=True, block_message=""),
    ), patch(
        "app.retrieval.query_expansion.expand_query", return_value=["q"]
    ), patch("app.retrieval.hybrid_search.search", return_value=[]), patch(
        "app.retrieval.reranker.rerank", return_value=[]
    ), patch("app.agent.loop._groq_text", return_value="NO") as mock_groq, patch(
        "app.agent.loop.context_manager_assemble", return_value="ctx"
    ), patch("app.agent.confidence.evaluate", return_value=evaluate_out):
        mock_meta.return_value = MagicMock(sync_status="synced")
        out = run("repo", "Explain the whole system architecture please", None, max_iterations=1)

    assert out["answer"]
    assert mock_groq.called
    assert out.get("gated") is True


def test_groq_failure_retries_then_errors():
    from app.agent.llm_client import ProviderError

    with patch("app.agent.loop.semantic_cache_lookup", return_value=None), patch(
        "app.agent.loop.metadata_store.get", return_value=MagicMock(sync_status="synced")
    ), patch("app.retrieval.query_expansion.expand_query", return_value=["q"]), patch(
        "app.retrieval.hybrid_search.search", return_value=[{"chunk": "x", "chunk_metadata": {}, "score": 1.0}]
    ), patch(
        "app.retrieval.reranker.rerank",
        return_value=[{"chunk": "x", "chunk_metadata": {}, "score": 1.0}],
    ), patch(
        "app.agent.loop._groq_text", side_effect=ProviderError("down")
    ):
        out = run("repo", "What is Config?", None)

    assert out.get("gated") is True
    assert "Unable" in out["answer"] or "error" in out


def test_forward_stub_signatures():
    assert semantic_cache_lookup("r", "q") is None or isinstance(semantic_cache_lookup("r", "q"), dict)
    trimmed = context_manager_assemble([{"chunk": "a" * 100}], "", max_tokens=10)
    assert isinstance(trimmed, str)
    score, gated, _ = confidence_verify("ans", [], best_retrieval_score=0.2)
    assert isinstance(score, float)
    assert isinstance(gated, bool)


def test_run_output_contract():
    with patch("app.agent.loop.semantic_cache_lookup", return_value=None), patch(
        "app.agent.loop.metadata_store.get", return_value=MagicMock(sync_status="synced")
    ), patch("app.retrieval.query_expansion.expand_query", return_value=["login flow"]), patch(
        "app.retrieval.hybrid_search.search",
        return_value=[{"chunk": "def login(): pass", "chunk_metadata": {"file_path": "auth.py", "start_line": 1, "end_line": 2}, "score": 0.8}],
    ), patch(
        "app.retrieval.reranker.rerank",
        return_value=[{"chunk": "def login(): pass", "chunk_metadata": {"file_path": "auth.py", "start_line": 1, "end_line": 2}, "score": 0.9}],
    ), patch("app.agent.loop._groq_text", side_effect=["YES", "Login is in `auth.py:1`."]), patch(
        "app.agent.loop.semantic_cache_store"
    ):
        out = run("repo", "How does login work?", "sess-1")

    assert set(["answer", "sources", "confidence_score", "gated"]).issubset(out.keys())
    assert isinstance(out["answer"], str)
