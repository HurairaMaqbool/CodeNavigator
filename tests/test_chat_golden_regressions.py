# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Permanent regression tests for CodeNavigator chat quality (Issues #1–#8)."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.agent.confidence import GATED_FALLBACK_MESSAGE, VERIFY_SYSTEM_ERROR_MESSAGE
from app.agent.grounding import polish_claims
from app.agent.loop import (
    _aspect_markers_satisfied,
    _chunks_cover_question_topic,
    _handle_decide,
    _is_unusable_cached_answer,
    _retrieval_strong_enough,
    AgentContext,
    AgentState,
)
from app.retrieval.hybrid_search import search
from app.retrieval.query_expansion import decompose_retrieval_variants, expand_query
from app.retrieval.source_priority import prefer_implementation_hits, query_path_boost

GOLDEN_QUESTIONS = [
    "Why does Requests use urllib3 instead of implementing HTTP from scratch?",
    "How are retries and timeouts handled?",
    "What happens internally when requests.get(url) is called?",
    "If you wanted to add a custom transport layer or retry mechanism, where would you make changes?",
    "What does HTTPAdapter do?",
    "How are cookies persisted across requests?",
]

REASONING_MARKERS = (
    "because", "instead", "rather than", "maintain", "reuse", "rationale",
    "trade-off", "mature", "delegat", "reimplement",
)


def _src_hit(path: str, fn: str, text: str, score: float = 0.9) -> dict:
    return {
        "chunk": text,
        "chunk_metadata": {
            "file_path": path,
            "display_path": path,
            "function_name": fn,
            "start_line": 10,
            "end_line": 40,
        },
        "score": score,
    }


@pytest.mark.parametrize("question", GOLDEN_QUESTIONS)
def test_golden_questions_have_decomposed_variants(question: str):
    variants = decompose_retrieval_variants(question)
    assert question  # original always used in expand_query
    expanded = expand_query(question)
    assert expanded[0] == question
    if "retri" in question.lower() and "timeout" in question.lower():
        assert len(variants) >= 2


def test_query_path_boost_status_codes_and_ctx():
    q1 = "What status code helper structures does requests provide?"
    assert query_path_boost("src/requests/status_codes.py", q1) > 0
    assert query_path_boost("src/requests/models.py", q1) == 0.0

    q2 = "How does Flask manage application and request context?"
    assert query_path_boost("src/flask/ctx.py", q2) > 0

    q3 = "How are cookies stored and managed across requests?"
    assert query_path_boost("src/requests/cookies.py", q3) > 0
    assert query_path_boost("README.md", q3) < 0


def test_retries_timeouts_decomposition_covers_both_aspects():
    q = "How are retries and timeouts handled?"
    variants = decompose_retrieval_variants(q)
    joined = " ".join(variants).lower()
    assert "retry" in joined
    assert "timeout" in joined


def test_aspect_markers_satisfied_for_retries_and_timeouts():
    chunks = [
        _src_hit("src/requests/adapters.py", "__init__", "max_retries Retry urllib3", 0.9),
        _src_hit("src/requests/adapters.py", "send", "TimeoutSauce connect read timeout urlopen", 0.88),
    ]
    q = "How are retries and timeouts handled?"
    assert _aspect_markers_satisfied(q, chunks) is True
    assert _chunks_cover_question_topic(q, chunks) is True
    ctx = AgentContext(repo_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", job_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", question=q, chunks=chunks, best_retrieval_score=0.9)
    assert _retrieval_strong_enough(ctx) is True


def test_decide_fast_path_skips_llm_when_retrieval_strong():
    q = "How are retries and timeouts handled?"
    chunks = [
        _src_hit("src/requests/adapters.py", "__init__", "max_retries Retry urllib3", 0.9),
        _src_hit("src/requests/adapters.py", "send", "TimeoutSauce connect read timeout urlopen", 0.88),
        _src_hit("src/requests/adapters.py", "build_response", "extra context", 0.7),
        _src_hit("src/requests/sessions.py", "request", "extra context", 0.65),
    ]
    ctx = AgentContext(
        repo_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        job_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        question=q,
        chunks=chunks,
        best_retrieval_score=0.9,
        query_variants=expand_query(q),
        iteration=0,
        max_iterations=3,
    )
    with patch("app.agent.loop._groq_text") as mock_llm:
        next_state = _handle_decide(ctx)
    assert next_state == AgentState.FINALIZE
    assert ctx.enough_evidence is True
    mock_llm.assert_not_called()


def test_why_query_polish_injects_reasoning_claim():
    chunks = [
        _src_hit("README.md", "", "requests builds on urllib3 to reuse a mature HTTP stack", 0.95),
        _src_hit("src/requests/adapters.py", "HTTPAdapter", "PoolManager urllib3 init_poolmanager", 0.9),
    ]
    claims = [{
        "claim": "HTTPAdapter constructs a urllib3 PoolManager in init_poolmanager.",
        "citation": {"file_path": "src/requests/adapters.py", "start_line": 239, "end_line": 267},
    }]
    out = polish_claims(claims, chunks, GOLDEN_QUESTIONS[0])
    text = " ".join(c["claim"] for c in out).lower()
    assert any(m in text for m in REASONING_MARKERS) or "readme" in text or "mature" in text


def test_prefer_implementation_never_leads_with_tests():
    hits = [
        _src_hit("tests/test_cookies.py", "test_cookies", "assert cookie jar", 0.99),
        _src_hit("src/requests/sessions.py", "merge_cookies", "merge_cookies session jar", 0.8),
    ]
    out = prefer_implementation_hits(hits, "How are cookies persisted across requests?")
    assert "tests/" not in (out[0]["chunk_metadata"]["display_path"])


def test_unusable_cache_rejects_verify_system_error():
    payload = {"answer": VERIFY_SYSTEM_ERROR_MESSAGE, "gated": True, "sources": []}
    assert _is_unusable_cached_answer(payload) is True


def test_unusable_cache_rejects_gated_fallback():
    payload = {"answer": GATED_FALLBACK_MESSAGE, "gated": True, "sources": []}
    assert _is_unusable_cached_answer(payload) is True


def test_user_messages_never_expose_verify_system_error_token():
    assert "verify_system_error" not in VERIFY_SYSTEM_ERROR_MESSAGE.lower()
    assert "verify_system_error" not in GATED_FALLBACK_MESSAGE.lower()


def test_hybrid_search_deterministic_ordering():
    """Same query twice must return identical top paths (Issue #5 non-determinism)."""
    repo = "b4f947369301e4e0681a5f878604aa39c14efce4fbd98648e3722afd9f6380ee"
    q = "HTTPAdapter send urlopen retries"
    try:
        a = search(repo, q, top_k=5)
        b = search(repo, q, top_k=5)
    except Exception:
        pytest.skip("indexed requests repo unavailable")
    paths_a = [
        (h.get("chunk_metadata") or {}).get("display_path")
        for h in a
    ]
    paths_b = [
        (h.get("chunk_metadata") or {}).get("display_path")
        for h in b
    ]
    assert paths_a == paths_b


def test_ensure_multipart_claims_injects_missing_aspect():
    from app.agent.grounding import ensure_multipart_claims

    chunks = [
        _src_hit("src/requests/adapters.py", "__init__", "max_retries Retry urllib3", 0.9),
        _src_hit("src/requests/adapters.py", "send", "TimeoutSauce connect read timeout urlopen", 0.88),
    ]
    claims = [{
        "claim": "HTTPAdapter.send resolves timeouts before urlopen.",
        "citation": {"file_path": "src/requests/adapters.py", "start_line": 681, "end_line": 706},
    }]
    q = "How are retries and timeouts handled?"
    out = ensure_multipart_claims(claims, chunks, q)
    text = " ".join(c["claim"] for c in out).lower()
    assert "retry" in text or "max_retries" in text
    assert "timeout" in text


def test_flow_question_requires_dispatch_markers():
    q = "What happens internally when requests.get(url) is called?"
    weak = [_src_hit("README.md", "", "requests is a library", 0.9)]
    strong = [
        _src_hit("src/requests/api.py", "get", "requests.get delegates to session.request", 0.9),
        _src_hit("src/requests/sessions.py", "request", "session.request send adapter", 0.88),
        _src_hit("src/requests/adapters.py", "send", "conn.urlopen PreparedRequest", 0.87),
    ]
    assert _chunks_cover_question_topic(q, weak) is False
    assert _chunks_cover_question_topic(q, strong) is True
