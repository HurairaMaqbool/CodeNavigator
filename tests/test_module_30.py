# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Module #30 — state_stream SSE broadcaster tests."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock


from app.api.state_stream import (
    STATE_LABELS,
    STREAM_DONE_SENTINEL,
    emit,
    reset_session,
    stream,
)
from app.agent.loop import AgentContext, AgentState, _transition


def _parse_sse(chunk: str) -> dict:
    assert chunk.startswith("data: ")
    return json.loads(chunk[len("data: "):].strip())


def test_emit_stream_contract():
    sid = "sess-1"
    reset_session(sid)
    emit(sid, "ACT")
    emit(sid, "RESPOND")

    chunks = list(stream(sid))
    assert len(chunks) == 2
    first = _parse_sse(chunks[0])
    assert set(first.keys()) == {"state", "label", "timestamp"}
    assert first["state"] == "ACT"
    assert first["label"] == STATE_LABELS["ACT"]
    second = _parse_sse(chunks[1])
    assert second["state"] == "RESPOND"


def test_labels_are_human_readable():
    for state, label in STATE_LABELS.items():
        assert state not in label
        assert "…" in label or label.endswith("…") or "..." in label or len(label) > 10


def test_transition_emits_real_states():
    ctx = AgentContext(repo_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", question="q", session_id="sess-t")
    reset_session("sess-t")
    _transition(ctx, AgentState.PLAN)
    _transition(ctx, AgentState.RESPOND)

    chunks = list(stream("sess-t"))
    states = [_parse_sse(c)["state"] for c in chunks]
    assert states[0] == "INTAKE"
    assert "PLAN" in states
    assert states[-1] == "RESPOND"


def test_async_stream_stops_on_disconnect():
    sid = "sess-disc"
    reset_session(sid)
    emit(sid, "PLAN")

    request = MagicMock()
    request.is_disconnected = AsyncMock(return_value=True)

    from app.api.state_stream import async_stream

    async def _collect():
        chunks = []
        async for chunk in async_stream(sid, request):
            chunks.append(chunk)
        return chunks

    import asyncio

    chunks = asyncio.run(_collect())
    assert chunks == []


def test_done_sentinel_constant():
    assert STREAM_DONE_SENTINEL == "[DONE]"


def test_emit_publishes_to_redis_when_available(monkeypatch):
    """Multi-replica path: emit publishes JSON to cn:sse:{session_id}."""
    published: list[tuple[str, str]] = []

    class _FakeRedis:
        def publish(self, channel: str, message: str) -> int:
            published.append((channel, message))
            return 1

    monkeypatch.setattr("app.redis_client.get_redis", lambda: _FakeRedis())
    sid = "sess-redis"
    reset_session(sid)
    emit(sid, "ACT")
    emit(sid, "RESPOND")
    assert len(published) >= 2
    channel, raw = published[0]
    assert channel == f"cn:sse:{sid}"
    payload = json.loads(raw)
    assert payload["state"] == "ACT"
    assert "origin" in payload
    # Local queue still receives events (single-process path).
    chunks = list(stream(sid))
    assert _parse_sse(chunks[0])["state"] == "ACT"
    assert _parse_sse(chunks[-1])["state"] == "RESPOND"
