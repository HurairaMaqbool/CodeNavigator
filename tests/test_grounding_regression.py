# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""
Permanent regression suite — Layered Grounding System (FINALIZE + VERIFY).

Re-run after any prompt/model change to prove grounding still holds.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.agent.claim_verification import verify_claims_batch
from app.agent.confidence import evaluate_structured_claims
from app.agent.grounding import (
    is_abstention_claim,
    is_factual_claim,
    parse_finalize_json,
    render_claims_markdown,
)
from app.config import settings

FIXTURES = Path(__file__).parent / "fixtures" / "grounding_eval.json"


@pytest.fixture
def eval_cases() -> list[dict]:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


def test_parse_finalize_json_good_shape():
    raw = json.dumps({
        "claims": [
            {
                "claim": "Session.send dispatches the prepared request.",
                "citation": {
                    "file_path": "src/requests/sessions.py",
                    "start_line": 573,
                    "end_line": 598,
                },
            }
        ]
    })
    claims = parse_finalize_json(raw)
    assert len(claims) == 1
    assert claims[0]["citation"]["start_line"] == 573


def test_parse_finalize_json_strips_fences():
    inner = '{"claims": [{"claim": "x", "citation": null}]}'
    raw = f"```json\n{inner}\n```"
    assert len(parse_finalize_json(raw)) == 1


def test_render_claims_inline_citations():
    claims = [{
        "claim": "Auth validates tokens.",
        "citation": {"file_path": "src/auth.py", "start_line": 10, "end_line": 12},
    }]
    md = render_claims_markdown(claims)
    assert "`src/auth.py:10-12`" in md
    assert "Auth validates tokens." in md


def test_abstention_claim_detected():
    claim = {
        "claim": "The context does not include retry backoff — I cannot confirm that behavior.",
        "citation": None,
    }
    assert is_abstention_claim(claim) is True
    assert is_factual_claim(claim) is False


def test_evaluate_structured_honest_abstention_passes():
    claims = [{
        "claim": "Insufficient context: indexed chunks show Session.send but not urllib3 Retry wiring.",
        "citation": None,
    }]
    verification = {"results": [{"index": 0, "supported": True, "structural_ok": True}]}
    out = evaluate_structured_claims(claims, "", "repo1", verification)
    assert out["gated"] is False
    assert "Insufficient context" in out["answer"]
    assert out["confidence_score"] >= settings.MIN_CONFIDENCE_SCORE


def test_evaluate_structured_gates_unsupported_factual():
    claims = [{
        "claim": "Fake mechanism in mystery module.",
        "citation": {"file_path": "src/fake.py", "start_line": 1, "end_line": 5},
    }]
    verification = {
        "results": [{
            "index": 0,
            "supported": False,
            "structural_ok": False,
            "similarity": 0.1,
        }],
        "verified_count": 0,
        "factual_count": 1,
    }
    out = evaluate_structured_claims(claims, "raw", "repo1", verification)
    assert out["gated"] is True


@pytest.mark.parametrize("case_id", [
    "session_send_mechanism",
    "http_basic_auth_location",
    "urllib3_poolmanager_role",
    "retry_backoff_abstain",
    "graphql_support_abstain",
])
def test_grounding_eval_fixture_contract(case_id: str, eval_cases: list[dict]):
    """Each fixture case defines claims + expected gating/abstention behavior."""
    case = next(c for c in eval_cases if c["id"] == case_id)
    claims = case["claims"]
    verification = case["verification"]

    for cite in claims:
        c = cite.get("citation")
        if c:
            assert c.get("start_line"), f"{case_id}: missing start_line"
            assert "path/to" not in c.get("file_path", ""), f"{case_id}: placeholder path"

    out = evaluate_structured_claims(
        claims,
        render_claims_markdown(claims),
        "eval-repo",
        verification,
    )
    assert out["gated"] is case["expect_gated"], case.get("note", case_id)
    if case.get("expect_abstention"):
        assert is_abstention_claim(claims[0])


def test_verify_claims_batch_mocked_embedding(eval_cases: list[dict]):
    """Atomic verification stays bounded — single embed batch, no per-claim LLM."""
    case = next(c for c in eval_cases if c["id"] == "session_send_mechanism")
    claims = case["claims"]

    with patch("app.agent.claim_verification.fetch_cited_text", return_value="def send(): pass"), patch(
        "app.agent.claim_verification._structural_ok", return_value=True,
    ), patch(
        "app.agent.claim_verification._verify_embedding_batch",
        return_value=([0.85] * len(claims), None),
    ):
        result = verify_claims_batch(claims, "eval-repo")

    assert result["factual_count"] == len(claims)
    assert result["verified_count"] == len(claims)
    assert result["latency_ms"] >= 0
    assert all(r["supported"] for r in result["results"])


def test_partial_failure_strips_unsupported_claim(eval_cases: list[dict]):
    case = next(c for c in eval_cases if c["id"] == "partial_verify_strip")
    out = evaluate_structured_claims(
        case["claims"],
        render_claims_markdown(case["claims"]),
        "eval-repo",
        case["verification"],
    )
    assert out["gated"] is False
    assert "asyncio" not in out["answer"].lower()
    assert "could not be verified" in out["answer"] or "HTTPAdapter" in out["answer"]


def test_finalize_prompt_includes_few_shot_and_json():
    from app.agent.prompts.finalize_prompt import finalize_prompt, finalize_system_prompt

    out = finalize_prompt({"question": "Q?", "assembled_context": "ctx"})
    assert "RESPOND WITH JSON ONLY" in out
    assert "FEW-SHOT GUIDANCE" in out or "EXAMPLE — GOOD" in out
    assert "ANTI-PATTERNS" in out or "EXAMPLE — BAD" in out
    assert "Use ONLY the provided code context" in out
    assert "JSON" in finalize_system_prompt()
