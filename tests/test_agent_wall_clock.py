# Copyright (c) 2026 Huraira Maqbool
"""Wall-clock and rate-limit sleep budget regressions."""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from app.agent.llm_client import RateLimitError
from app.agent.loop import AgentContext, _groq_text
from app.config import settings


def test_groq_rate_limit_sleep_respects_wall_clock_budget():
    ctx = AgentContext(
        repo_id="r",
        job_id="r",
        question="q",
        started_monotonic=time.monotonic() - 26.0,
    )
    mock_llm = MagicMock()
    mock_llm.stream_text.side_effect = RateLimitError(
        "Groq API rate limit exceeded. Retry after 8s."
    )

    with patch("app.agent.loop.get_llm_client", return_value=mock_llm), patch(
        "app.agent.loop.time.sleep"
    ) as sleep_mock, patch.object(settings, "AGENT_MAX_SECONDS", 25), patch.object(
        settings, "AGENT_MAX_CUMULATIVE_RATE_LIMIT_SLEEP_S", 12.0
    ), patch.object(settings, "LLM_RATE_LIMIT_MAX_BACKOFF_S", 12.0), patch.object(
        settings, "GROQ_LLM_RATE_LIMIT_ATTEMPTS", 3
    ):
        with pytest.raises(RateLimitError, match="wall-clock budget"):
            _groq_text("sys", "user", purpose="finalize", ctx=ctx)

    sleep_mock.assert_not_called()


def test_groq_rate_limit_sleep_caps_to_remaining_budget():
    ctx = AgentContext(
        repo_id="r",
        job_id="r",
        question="q",
        started_monotonic=time.monotonic() - 5.0,
    )
    calls = {"n": 0}

    def _stream(*_a, **_k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RateLimitError("Groq API rate limit exceeded. Retry after 8s.")
        return ("OK", {"sdk_attempts": 1})

    mock_llm = MagicMock()
    mock_llm.stream_text.side_effect = _stream

    with patch("app.agent.loop.get_llm_client", return_value=mock_llm), patch(
        "app.agent.loop.time.sleep"
    ) as sleep_mock, patch.object(settings, "AGENT_MAX_SECONDS", 25), patch.object(
        settings, "AGENT_MAX_CUMULATIVE_RATE_LIMIT_SLEEP_S", 12.0
    ), patch.object(settings, "LLM_RATE_LIMIT_MAX_BACKOFF_S", 12.0), patch.object(
        settings, "GROQ_LLM_RATE_LIMIT_ATTEMPTS", 3
    ):
        out = _groq_text("sys", "user", purpose="finalize", ctx=ctx)

    assert out == "OK"
    assert sleep_mock.call_count == 1
    slept = sleep_mock.call_args[0][0]
    assert slept <= 12.0
