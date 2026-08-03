# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Claim verification edge cases — cited text fallback and audit logging."""
from __future__ import annotations

from unittest.mock import patch

from app.agent.claim_verification import (
    _check_claim_responsiveness,
    _retrieval_text_for_citation,
    fetch_cited_text,
    verify_claims_batch,
)
from app.agent.grounding import normalize_citation, parse_finalize_json


def test_retrieval_text_prefers_line_overlap():
    hits = [
        {
            "chunk": "def send(self): pass",
            "chunk_metadata": {
                "display_path": "src/requests/sessions.py",
                "start_line": 600,
                "end_line": 650,
            },
        },
        {
            "chunk": "class Session: ...",
            "chunk_metadata": {
                "display_path": "src/requests/sessions.py",
                "start_line": 100,
                "end_line": 200,
            },
        },
    ]
    text = _retrieval_text_for_citation(
        "src/requests/sessions.py", 610, 620, hits
    )
    assert "def send" in text


def test_retrieval_text_path_only_fallback():
    hits = [
        {
            "chunk": "poolmanager code",
            "chunk_metadata": {"display_path": "requests/packages/urllib3/poolmanager.py"},
        },
    ]
    text = _retrieval_text_for_citation(
        "requests/packages/urllib3/poolmanager.py",
        1,
        5,
        hits,
        path_only=True,
    )
    assert text == "poolmanager code"


def test_fetch_cited_text_uses_retrieval_hits_when_metadata_empty():
    hits = [
        {
            "chunk": "def validate(): return True",
            "chunk_metadata": {
                "display_path": "src/requests/models.py",
                "start_line": 10,
                "end_line": 40,
            },
        },
    ]
    with patch("app.agent.confidence._load_repo_metadata", return_value=[]), patch(
        "app.agent.confidence._clone_file_path", return_value=None
    ):
        text = fetch_cited_text(
            "repo-1",
            "src/requests/models.py",
            12,
            18,
            retrieval_hits=hits,
        )
    assert "validate" in text


def test_verify_logs_nonzero_cited_text_len():
    claims = [
        {
            "claim": "Session.send dispatches HTTP requests.",
            "citation": {
                "file_path": "src/requests/sessions.py",
                "start_line": 600,
                "end_line": 610,
            },
        },
    ]
    cited = "def send(self, request, **kwargs): pass"
    logged: list[dict] = []

    def _capture(**kwargs):
        if kwargs.get("event") == "claim_verify_check" or True:
            logged.append(kwargs)

    with patch("app.agent.claim_verification._structural_ok", return_value=True), patch(
        "app.agent.claim_verification.fetch_cited_text", return_value=cited
    ), patch(
        "app.agent.claim_verification._verify_embedding_batch", return_value=([0.85], None)
    ), patch(
        "app.agent.claim_verification._log_verify_check",
        side_effect=lambda **kw: logged.append(kw),
    ):
        result = verify_claims_batch(claims, "repo-1")

    assert result["verified_count"] == 1
    assert logged
    assert logged[0]["cited_text_len"] == len(cited)


def test_verify_does_not_crash_on_string_citation():
    """Non-dict citations must not raise verify_system_error (Groq json_object drift)."""
    claims = [
        {
            "claim": "PreparedRequest wraps request data.",
            "citation": "src/requests/models.py:250-280",
        }
    ]
    with patch("app.agent.claim_verification._structural_ok", return_value=True), patch(
        "app.agent.claim_verification.fetch_cited_text", return_value="class PreparedRequest"
    ), patch(
        "app.agent.claim_verification._verify_embedding_batch", return_value=([0.9], None)
    ):
        result = verify_claims_batch(claims, "repo-1")
    assert result.get("verification_error") is not True
    assert result["verified_count"] == 1


def test_verify_does_not_crash_on_list_citation():
    claims = [
        {
            "claim": "PreparedRequest wraps request data.",
            "citation": [
                {
                    "file_path": "src/requests/models.py",
                    "start_line": 250,
                    "end_line": 280,
                }
            ],
        }
    ]
    with patch("app.agent.claim_verification._structural_ok", return_value=True), patch(
        "app.agent.claim_verification.fetch_cited_text", return_value="class PreparedRequest"
    ), patch(
        "app.agent.claim_verification._verify_embedding_batch", return_value=([0.9], None)
    ):
        result = verify_claims_batch(claims, "repo-1")
    assert result.get("verification_error") is not True
    assert result["verified_count"] == 1


def test_verify_known_good_finalize_output_isolated():
    raw = """{
      "claims": [
        {
          "claim": "PreparedRequest wraps request data for sending.",
          "citation": {"file_path": "src/requests/models.py", "start_line": 250, "end_line": 280}
        }
      ]
    }"""
    claims = parse_finalize_json(raw)
    cited = "class PreparedRequest(RequestEncodingMixin):"
    with patch("app.agent.claim_verification._structural_ok", return_value=True), patch(
        "app.agent.claim_verification.fetch_cited_text", return_value=cited
    ), patch(
        "app.agent.claim_verification._verify_embedding_batch", return_value=([0.88], None)
    ):
        result = verify_claims_batch(claims, "repo-1")
    assert result.get("verification_error") is not True
    assert result["verified_count"] == 1
    assert result["results"][0]["method"] == "embedding"


def test_normalize_citation_parses_inline_string():
    cit = normalize_citation("src/requests/models.py:250-280")
    assert cit == {
        "file_path": "src/requests/models.py",
        "start_line": 250,
        "end_line": 280,
    }


def test_embed_failure_falls_back_to_lexical_not_hard_gate():
    """Embedding failures degrade to lexical overlap — chat must not hard-gate."""
    claims = [
        {
            "claim": "PreparedRequest wraps request data.",
            "citation": {"file_path": "src/requests/models.py", "start_line": 250, "end_line": 280},
        }
    ]
    with patch("app.agent.claim_verification._structural_ok", return_value=True), patch(
        "app.agent.claim_verification.fetch_cited_text", return_value="class PreparedRequest"
    ), patch(
        "app.retrieval.embeddings.embed_batch",
        side_effect=RuntimeError("Cannot copy out of meta tensor"),
    ):
        result = verify_claims_batch(claims, "repo-1")
    assert result.get("verification_error") is not True
    assert result["verified_count"] >= 1
    assert result["results"][0]["method"] in ("lexical", "lexical_reroute")


# ── New test: Issue 10 fail-open gate ────────────────────────────────────────

def test_responsiveness_missing_inputs_returns_fail():
    """
    _check_claim_responsiveness must return FAIL (not YES) when either
    the claim or the question is empty/None.  This pins the fix for the
    fail-open default that was at line 744:
        if not claim or not question: return "YES"  # BUG — now returns "FAIL"
    """
    # Empty claim
    assert _check_claim_responsiveness("", "What does Session.send do?") == "FAIL"
    # Empty question
    assert _check_claim_responsiveness("Session.send dispatches HTTP.", "") == "FAIL"
    # Both empty
    assert _check_claim_responsiveness("", "") == "FAIL"
    # None-equivalent (falsy)
    assert _check_claim_responsiveness(None, "Some question?") == "FAIL"   # type: ignore[arg-type]
    assert _check_claim_responsiveness("Some claim.", None) == "FAIL"       # type: ignore[arg-type]
