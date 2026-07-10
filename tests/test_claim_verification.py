# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Claim verification edge cases — cited text fallback and audit logging."""
from __future__ import annotations

from unittest.mock import patch

from app.agent.claim_verification import (
    _retrieval_text_for_citation,
    fetch_cited_text,
    verify_claims_batch,
)


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
        "app.agent.claim_verification._verify_embedding_batch", return_value=[0.85]
    ), patch(
        "app.agent.claim_verification._log_verify_check",
        side_effect=lambda **kw: logged.append(kw),
    ):
        result = verify_claims_batch(claims, "repo-1")

    assert result["verified_count"] == 1
    assert logged
    assert logged[0]["cited_text_len"] == len(cited)
