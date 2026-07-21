# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Rate-limit and provider failure regression tests (Issue #9)."""
from __future__ import annotations

from app.agent.llm_client import RateLimitError
from app.agent.loop import AgentContext, _apply_provider_failure


def test_rate_limited_message_is_actionable_not_gated_technical():
    ctx = AgentContext(repo_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", job_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", question="q")
    msg = _apply_provider_failure(
        ctx,
        RateLimitError("Groq API rate limit exceeded. Retry after 25s"),
        phase="finalize",
    )
    assert ctx.rate_limited is True
    assert ctx.retry_after_s == 25.0
    assert "rate-limited" in msg.lower()
    assert "25" in msg
    assert "verify_system_error" not in msg.lower()
    assert "Gated response" not in msg


def test_provider_timeout_message_is_actionable():
    ctx = AgentContext(repo_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", job_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", question="q")
    msg = _apply_provider_failure(ctx, TimeoutError("timed out"), phase="decide")
    assert ctx.timed_out is True
    assert "slow" in msg.lower() or "specific" in msg.lower()
