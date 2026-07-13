# Copyright (c) 2026 Huraira Maqbool
from app.retrieval.query_expansion import (
    decompose_retrieval_variants,
    expand_query,
    needs_flow_tracing,
    question_aspect_markers,
    reasoning_retrieval_variants,
)


def test_reasoning_retrieval_variants_for_urllib3():
    variants = reasoning_retrieval_variants(
        "Why does Requests use urllib3 instead of implementing HTTP from scratch?"
    )
    joined = " ".join(variants).lower()
    assert "readme" in joined
    assert "urllib3" in joined


def test_decompose_retries_and_timeouts():
    variants = decompose_retrieval_variants("How are retries and timeouts handled?")
    assert len(variants) >= 2
    joined = " ".join(variants).lower()
    assert "retry" in joined
    assert "timeout" in joined


def test_question_aspect_markers_multi_part():
    aspects = question_aspect_markers("How are retries and timeouts handled?")
    names = {a[0] for a in aspects}
    assert names == {"retries", "timeouts"}


def test_needs_flow_tracing_requests_get():
    q = "What happens internally when requests.get(url) is called?"
    assert needs_flow_tracing(q)


def test_expand_query_includes_decomposed_variants(monkeypatch):
    monkeypatch.setattr(
        "app.retrieval.query_expansion.should_expand",
        lambda _q: False,
    )
    variants = expand_query("How are retries and timeouts handled?")
    assert variants[0] == "How are retries and timeouts handled?"
    assert len(variants) >= 3
