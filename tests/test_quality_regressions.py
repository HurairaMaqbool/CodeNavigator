# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Regression tests for production quality issues: retrieval, sources, diagrams."""
from __future__ import annotations

from unittest.mock import patch

import networkx as nx
import pytest

from app.agent.confidence import (
    assert_sources_match_answer,
    parse_citations,
    reconcile_sources_with_answer,
    sources_from_answer_citations,
    validate_sources,
)
from app.agent.loop import _chunks_cover_question_topic, _retrieval_strong_enough
from app.agent.loop import AgentContext
from app.graph.queries import get_subgraph
from app.retrieval.query_expansion import deterministic_expansions, expand_query, should_expand
from app.retrieval.reranker import rerank


POOLING_QUESTION = "How does connection pooling improve performance?"

RATIONALE_QUESTIONS = [
    POOLING_QUESTION,
    "How does keep-alive improve HTTP request performance?",
    "Why does connection reuse make requests faster?",
    "How does caching improve response time?",
    "Why does the adapter layer improve throughput?",
]


def _pooling_hit(path: str, fn: str, score: float) -> dict:
    return {
        "chunk": f"def {fn}(): pass  # pool manager connection reuse",
        "chunk_metadata": {
            "file_path": path,
            "display_path": path,
            "function_name": fn,
            "start_line": 10,
            "end_line": 40,
        },
        "score": score,
    }


def test_should_expand_skips_pooling_how_question():
    assert should_expand(POOLING_QUESTION) is False


def test_deterministic_expansions_include_poolmanager_terms():
    variants = deterministic_expansions(POOLING_QUESTION)
    joined = " ".join(variants).lower()
    assert "poolmanager" in joined or "init_poolmanager" in joined
    assert "adapters" in joined


def test_expand_query_includes_deterministic_variants_without_llm():
    with patch("app.retrieval.query_expansion.should_expand", return_value=False):
        out = expand_query(POOLING_QUESTION)
    assert POOLING_QUESTION in out
    assert len(out) >= 2
    assert any("poolmanager" in v.lower() for v in out)


def test_rerank_boosts_pooling_chunks_over_send():
    hits = [
        _pooling_hit("tests/test_requests.py", "test_pool", 0.5),
        _pooling_hit("src/requests/adapters.py", "init_poolmanager", 0.5),
        _pooling_hit("src/requests/adapters.py", "get_connection_with_tls_context", 0.5),
        _pooling_hit("src/requests/sessions.py", "send", 0.5),
    ]
    with patch("app.retrieval.reranker.settings.ENABLE_RERANKER", True), patch(
        "app.retrieval.reranker.get_model",
    ) as mock_get_model:
        mock_get_model.return_value.predict.return_value = [0.5, 0.5, 0.5, 0.5]
        ranked = rerank(POOLING_QUESTION, hits, top_n=4)
    top_fns = [
        (h["chunk_metadata"].get("function_name") or "").lower() for h in ranked[:2]
    ]
    assert any("pool" in fn or "tls" in fn or "init" in fn for fn in top_fns)
    assert top_fns[0] != "send"


def test_chunks_cover_question_topic_rejects_send_only_context():
    chunks = [
        _pooling_hit("src/requests/sessions.py", "send", 0.9),
    ]
    assert _chunks_cover_question_topic(POOLING_QUESTION, chunks) is False


def test_chunks_cover_question_topic_accepts_pooling_context():
    chunks = [
        _pooling_hit("src/requests/adapters.py", "init_poolmanager", 0.8),
        _pooling_hit("src/requests/adapters.py", "get_connection_with_tls_context", 0.75),
    ]
    assert _chunks_cover_question_topic(POOLING_QUESTION, chunks) is True


def test_retrieval_fast_path_blocked_for_irrelevant_pooling_context():
    ctx = AgentContext(
        repo_id="repo1",
        job_id="repo1",
        question=POOLING_QUESTION,
        chunks=[_pooling_hit("src/requests/sessions.py", "send", 0.9)],
        best_retrieval_score=0.9,
        query_variants=[POOLING_QUESTION],
        iteration=0,
    )
    assert _retrieval_strong_enough(ctx) is False


@pytest.mark.parametrize("question", RATIONALE_QUESTIONS)
def test_rationale_questions_have_deterministic_or_skip_expansion(question: str):
    """How/why performance questions should not rely on vague LLM expansion alone."""
    det = deterministic_expansions(question)
    skip_llm = not should_expand(question)
    assert skip_llm or len(det) >= 1


def test_validate_sources_returns_all_valid_rows():
    sources = [
        {
            "file_path": f"src/module/file_{i}.py",
            "function_name": f"fn_{i}",
            "start_line": 10 + i,
            "end_line": 20 + i,
            "lines": f"{10 + i}-{20 + i}",
        }
        for i in range(5)
    ]
    with patch("app.agent.confidence.check_file_existence", return_value=True), patch(
        "app.agent.confidence.check_line_bounds", return_value=True,
    ):
        out = validate_sources(sources, "repo1")
    assert len(out) == 5


def test_sources_from_answer_citations_dedupes_by_line_range():
    answer = (
        "First `src/a.py:10-20` and second `src/a.py:30-40` "
        "and repeat `src/a.py:10-20`."
    )
    cites = parse_citations(answer)
    sources = sources_from_answer_citations(answer, "repo1")
    assert len(cites) >= 2
    assert len(sources) == 2


def test_reconcile_sources_matches_inline_citations():
    answer = (
        "Pooling reuses sockets `src/requests/adapters.py:85-120` "
        "via PoolManager `src/requests/adapters.py:200-240`."
    )
    claims_sources = [{"file_path": "src/requests/adapters.py", "start_line": 85, "end_line": 120, "lines": "85-120"}]
    with patch("app.agent.confidence.check_file_existence", return_value=True), patch(
        "app.agent.confidence.check_line_bounds", return_value=True,
    ):
        reconciled = reconcile_sources_with_answer(answer, claims_sources, "repo1")
    assert len(reconciled) == 2
    assert assert_sources_match_answer(answer, reconciled, repo_id="repo1") is True


def test_assert_sources_match_logs_mismatch():
    answer = "See `src/a.py:1-5` and `src/b.py:2-8`."
    sources = [{"file_path": "src/a.py", "start_line": 1, "end_line": 5, "lines": "1-5"}]
    assert assert_sources_match_answer(answer, sources, repo_id="repo1") is False


def _build_hub_graph() -> tuple[str, nx.DiGraph]:
    """Hub node with many callers and callees."""
    g = nx.DiGraph()
    hub = "requests/sessions.py:Session.send"
    g.add_node(hub, name="Session.send", path="requests/sessions.py", type="method")
    for i in range(120):
        caller = f"pkg/mod_{i}.py:call_{i}"
        callee = f"pkg/util_{i}.py:helper_{i}"
        g.add_node(caller, name=f"call_{i}", path=f"pkg/mod_{i}.py", type="function")
        g.add_node(callee, name=f"helper_{i}", path=f"pkg/util_{i}.py", type="function")
        g.add_edge(caller, hub, call_count=1)
        g.add_edge(hub, callee, call_count=1)
    return hub, g


def test_get_subgraph_fanout_cap_bounds_hub_symbol():
    hub, graph = _build_hub_graph()
    with patch("app.graph.queries._get_graph", return_value=graph):
        sub = get_subgraph("repo1", "Session.send", direction="both", max_depth=2, max_fanout=10)
    assert len(sub["nodes"]) <= 1 + 10 * 2 + 10  # entry + 2 layers capped
    assert sub["truncated_count"] > 0
    assert len(sub["hidden_neighbors"]) == sub["truncated_count"]
    assert len(sub["nodes"]) < 50


def test_get_subgraph_downstream_smaller_than_both():
    hub, graph = _build_hub_graph()
    with patch("app.graph.queries._get_graph", return_value=graph):
        both = get_subgraph("repo1", "Session.send", direction="both", max_depth=1, max_fanout=8)
        down = get_subgraph("repo1", "Session.send", direction="downstream", max_depth=1, max_fanout=8)
    assert len(down["nodes"]) <= len(both["nodes"])


def test_hidden_neighbors_include_metadata():
    hub, graph = _build_hub_graph()
    with patch("app.graph.queries._get_graph", return_value=graph):
        sub = get_subgraph("repo1", "Session.send", direction="downstream", max_depth=1, max_fanout=5)
    assert sub["hidden_neighbors"]
    sample = sub["hidden_neighbors"][0]
    assert {"parent_name", "name", "direction", "path"} <= set(sample.keys())


def test_hidden_caller_neighbors_id_is_caller_not_parent():
    """Caller hidden rows must reference the predecessor node, not the hub (parent)."""
    g = nx.DiGraph()
    hub = "src/requests/api.py:get"
    g.add_node(hub, name="get", path="src/requests/api.py", type="function")
    for i in range(20):
        caller = f"src/caller_{i}.py:fn_{i}"
        g.add_node(caller, name=f"fn_{i}", path=f"src/caller_{i}.py", type="function")
        g.add_edge(caller, hub, call_count=1)
    with patch("app.graph.queries._get_graph", return_value=g):
        sub = get_subgraph("repo1", "get", direction="upstream", max_depth=1, max_fanout=5)
    caller_rows = [h for h in sub["hidden_neighbors"] if h["direction"] == "caller"]
    assert caller_rows
    for row in caller_rows:
        assert row["id"] != row["parent_id"]
    keys = {(h["parent_id"], h["id"], h["direction"]) for h in sub["hidden_neighbors"]}
    assert len(keys) == len(sub["hidden_neighbors"])


def test_confidence_varies_with_retrieval_and_completeness():
    from app.agent.confidence import evaluate

    shallow = (
        "The Session class exists. `src/requests/sessions.py:134-152`"
    )
    detailed = (
        "api.py get calls request. `src/requests/api.py:74-87`\n"
        "Session.send dispatches via adapter. `src/requests/sessions.py:700-720`\n"
        "HTTPAdapter.send uses urlopen. `src/requests/adapters.py:512-553`"
    )
    q = "Which modules handle request creation, transport, and response parsing?"
    with patch("app.agent.confidence.check_file_existence", return_value=True), patch(
        "app.agent.confidence.check_line_bounds", return_value=True
    ), patch("app.agent.confidence.check_graph_consistency", return_value=True):
        shallow_score = evaluate(
            shallow, "repo1", top_retrieval_score=0.55, question=q,
        )["confidence_score"]
        detailed_score = evaluate(
            detailed, "repo1", top_retrieval_score=0.92, question=q,
        )["confidence_score"]
    assert shallow_score < detailed_score
    assert shallow_score < 10.0


def test_question_aspect_markers_modules_triplet():
    from app.retrieval.query_expansion import question_aspect_markers

    q = "Which modules are responsible for request creation, transport, and response parsing?"
    aspects = question_aspect_markers(q)
    names = {a[0] for a in aspects}
    assert {"creation", "transport", "parsing"} <= names
