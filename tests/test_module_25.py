# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Module #25 — context_manager budget + compression tests."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.agent.context_manager import (
    KEEP_RECENT_TOOL_RESULTS,
    OBSERVE_TOOL_RESULT_TOKEN_BUDGET,
    compress,
    compress_older_tool_results,
    memory_token_count,
    should_compress,
)
from app.agent.llm_client import LLMResponse


def _tool_entry(text: str, *, token_count: int | None = None) -> dict:
    entry = {
        "role": "user",
        "content": [{"type": "tool_result", "content": text}],
    }
    if token_count is not None:
        entry["token_count"] = token_count
    return entry


def test_should_compress_uses_fixed_budget():
    under = [_tool_entry("x", token_count=2000), _tool_entry("y", token_count=2000)]
    over = [_tool_entry("x", token_count=2500), _tool_entry("y", token_count=2500)]
    assert should_compress(under) is False
    assert should_compress(over) is True
    assert OBSERVE_TOOL_RESULT_TOKEN_BUDGET == 4000


def test_compress_keeps_recent_verbatim():
    memory = [
        _tool_entry("old1", token_count=2500),
        _tool_entry("old2", token_count=2500),
        _tool_entry("recent1", token_count=100),
        _tool_entry("recent2", token_count=100),
    ]
    mock_llm = MagicMock()
    mock_llm.create.return_value = LLMResponse(
        content=[{"type": "text", "text": "Dense summary of old outputs."}],
        stop_reason="end_turn",
        usage={},
    )

    with patch("app.agent.context_manager.get_llm_client", return_value=mock_llm), patch(
        "app.agent.context_manager.compress_prompt", return_value="prompt"
    ) as mock_prompt:
        out = compress(memory)

    assert out is memory
    mock_prompt.assert_called_once()
    assert "Compressed prior" in memory[0]["content"][0]["text"]
    assert memory[2]["content"][0]["content"] == "recent1"
    assert memory[3]["content"][0]["content"] == "recent2"
    assert mock_llm.create.call_count == 1


def test_compress_skips_when_under_budget():
    memory = [_tool_entry("small", token_count=100)]
    with patch("app.agent.context_manager.get_llm_client") as mock_llm:
        compress(memory)
    mock_llm.assert_not_called()


def test_compress_fallback_truncates_oldest_on_llm_failure():
    memory = [
        _tool_entry("drop-me", token_count=3000),
        _tool_entry("keep", token_count=3000),
        _tool_entry("recent", token_count=50),
        _tool_entry("recent2", token_count=50),
    ]
    mock_llm = MagicMock()
    mock_llm.create.side_effect = RuntimeError("groq down")

    with patch("app.agent.context_manager.get_llm_client", return_value=mock_llm):
        compress(memory)

    assert len(memory) == 3
    assert memory[0]["content"][0]["content"] == "keep"
    assert mock_llm.create.call_count == 2  # retry once


def test_legacy_compress_older_tool_results_ec9_shape():
    messages = [
        {"role": "user", "content": [{"type": "tool_result", "content": "result1"}]},
        {"role": "user", "content": [{"type": "tool_result", "content": "result2"}]},
        {"role": "user", "content": [{"type": "tool_result", "content": "result3"}]},
        {"role": "user", "content": [{"type": "tool_result", "content": "result4"}]},
    ]
    mock_llm = MagicMock()
    mock_llm.create.return_value = LLMResponse(
        content=[{"type": "text", "text": "Summary of old results"}],
        stop_reason="end_turn",
        usage={},
    )

    with patch("app.agent.context_manager.get_llm_client", return_value=mock_llm):
        compress_older_tool_results(messages, keep_last_n=KEEP_RECENT_TOOL_RESULTS)

    assert "Compressed prior" in messages[0]["content"][0]["text"]
    assert messages[2]["content"][0]["content"] == "result3"
    assert messages[3]["content"][0]["content"] == "result4"
