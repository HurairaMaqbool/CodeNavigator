# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Regression tests — structured FINALIZE JSON must never leak to users."""
from __future__ import annotations

from app.agent.confidence import GATED_FALLBACK_MESSAGE
from app.agent.grounding import (
    looks_like_leaked_finalize_json,
    parse_finalize_json,
    render_claims_markdown,
)
from app.agent.response_firewall import has_forbidden_leak


TRUNCATED_JSON = """{
  "claims": [
    {
      "claim": "Connection pooling reuses sockets.",
      "citation": {"file_path": "src/requests/adapters.py", "start_line": 85, "end_line": 120}
    },
    {
      "claim": "PoolManager is initialized in init_poolmanager.",
      "citation":"""


VALID_JSON = """{
  "claims": [
    {
      "claim": "PoolManager is initialized in init_poolmanager.",
      "citation": {"file_path": "src/requests/adapters.py", "start_line": 85, "end_line": 120}
    }
  ]
}"""


def test_truncated_json_fails_parse():
    assert parse_finalize_json(TRUNCATED_JSON) == []


def test_valid_json_renders_prose_not_raw():
    claims = parse_finalize_json(VALID_JSON)
    rendered = render_claims_markdown(claims)
    assert "claims" not in rendered
    assert "adapters.py" in rendered
    assert not looks_like_leaked_finalize_json(rendered)


def test_parse_accepts_inline_string_citation():
    raw = """{
      "claims": [
        {
          "claim": "PoolManager is initialized in init_poolmanager.",
          "citation": "src/requests/adapters.py:85-120"
        }
      ]
    }"""
    claims = parse_finalize_json(raw)
    assert len(claims) == 1
    assert claims[0]["citation"]["file_path"] == "src/requests/adapters.py"
    assert claims[0]["citation"]["start_line"] == 85


def test_leak_detector_catches_raw_finalize_json():
    assert looks_like_leaked_finalize_json(TRUNCATED_JSON)
    assert looks_like_leaked_finalize_json(VALID_JSON)
    assert not looks_like_leaked_finalize_json(
        "Pooling reuses connections `src/requests/adapters.py:85-120`."
    )


def test_response_firewall_flags_structured_json():
    assert has_forbidden_leak(TRUNCATED_JSON)
    assert not has_forbidden_leak(GATED_FALLBACK_MESSAGE)


def test_finalize_handler_gates_on_json_parse_failure():
    from unittest.mock import patch

    from app.agent.loop import AgentContext, AgentState, _handle_finalize

    ctx = AgentContext(
        repo_id="repo1",
        job_id="repo1",
        question="How does pooling work?",
        chunks=[{
            "chunk": "def init_poolmanager(): pass",
            "chunk_metadata": {
                "file_path": "src/requests/adapters.py",
                "start_line": 85,
                "end_line": 120,
            },
            "score": 0.9,
        }],
    )

    with patch("app.agent.loop._groq_text", side_effect=[TRUNCATED_JSON, TRUNCATED_JSON]):
        state = _handle_finalize(ctx)

    assert state == AgentState.RESPOND
    assert ctx.gated is True
    assert ctx.answer == GATED_FALLBACK_MESSAGE
    assert ctx.sources == []
    assert looks_like_leaked_finalize_json(ctx.answer) is False
