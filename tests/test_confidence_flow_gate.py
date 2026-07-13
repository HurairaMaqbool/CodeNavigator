# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Confidence scoring — flow depth and why-question quality factors."""
from __future__ import annotations

from unittest.mock import patch

from app.agent.confidence import (
    MAX_DISPLAY_CONFIDENCE,
    evaluate,
    evaluate_structured_claims,
    flow_answer_completeness_factor,
)


def test_flow_factor_penalizes_shallow_requests_get_answer():
    q = "What happens internally when requests.get(url) is called?"
    shallow = (
        "get calls request. `src/requests/api.py:74-87`\n"
        "request_url returns url. `src/requests/adapters.py:565-597`"
    )
    deep = (
        "get calls request. `src/requests/api.py:74-87`\n"
        "Session.send dispatches. `src/requests/sessions.py:700-720`\n"
        "adapter send urlopen. `src/requests/adapters.py:512-553`"
    )
    assert flow_answer_completeness_factor(q, shallow) < 0.55
    assert flow_answer_completeness_factor(q, deep) >= 0.75


def test_evaluate_never_returns_perfect_ten_for_typical_verified_answer():
    answer = (
        "Uses urllib3 adapter. `src/requests/adapters.py:158-183`\n"
        "Simple API. `README.md:1-76`"
    )
    q = "Why does Requests use urllib3?"
    with patch("app.agent.confidence.check_file_existence", return_value=True), patch(
        "app.agent.confidence.check_line_bounds", return_value=True
    ), patch("app.agent.confidence.check_graph_consistency", return_value=True):
        score = evaluate(
            answer,
            "repo1",
            top_retrieval_score=0.95,
            question=q,
        )["confidence_score"]
    assert score <= MAX_DISPLAY_CONFIDENCE
    assert score < 10.0


def test_structured_eval_gates_incomplete_flow():
    q = "What happens internally when requests.get(url) is called?"
    claims = [
        {
            "claim": "get calls request.",
            "citation": "src/requests/api.py:74-87",
            "type": "factual",
        },
        {
            "claim": "request_url returns the url.",
            "citation": "src/requests/adapters.py:565-597",
            "type": "factual",
        },
    ]
    verification = {
        "results": [
            {"index": 0, "supported": True, "structural_ok": True},
            {"index": 1, "supported": True, "structural_ok": True},
        ],
        "verified_count": 2,
    }
    out = evaluate_structured_claims(
        claims,
        "",
        "repo1",
        verification,
        top_retrieval_score=0.62,
        question=q,
    )
    assert out["gated"] is True
    assert out["confidence_score"] < 10.0
