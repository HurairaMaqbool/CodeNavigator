# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/api/state_stream.py
-----------------------
Module #30 — Live agent state-transition broadcaster via Server-Sent Events.

Uses Starlette/FastAPI ``StreamingResponse`` with ``media_type=text/event-stream``
(stdlib + framework only — no sse-starlette dependency).

Delivery:
- Always buffers into an in-process ``queue.Queue`` (single-replica / tests).
- When Redis is available, also publishes to ``cn:sse:{session_id}`` so a
  different API replica can serve the open SSE connection (multi-replica).
- Subscribers ignore events whose ``origin`` matches this process to avoid
  duplicate frames when Redis echoes a locally published event.
"""
from __future__ import annotations

import asyncio
import json
import queue
import threading
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.observability.logging_config import logger

# Stream termination sentinel (internal — never sent as a user-visible label).
STREAM_DONE_SENTINEL = "[DONE]"

# Pre-approved human labels — never expose raw enum names to the frontend.
STATE_LABELS: dict[str, str] = {
    "INTAKE": "Preparing your request…",
    "PLAN": "Understanding your question…",
    "ACT": "Searching the codebase…",
    "OBSERVE": "Reading relevant code…",
    "DECIDE": "Reasoning about the answer…",
    "FINALIZE": "Writing the response…",
    "VERIFY": "Double-checking citations…",
    "RESPOND": "Finalizing…",
}

REDIS_CHANNEL_PREFIX = "cn:sse:"
_PROCESS_ORIGIN = uuid.uuid4().hex

_SESSION_QUEUES: dict[str, queue.Queue[dict[str, Any]]] = {}
_SESSION_BRIDGES: dict[str, threading.Thread] = {}
_SESSION_LOCK = threading.Lock()

# Tunables from settings — not hardcoded module constants.
_QUEUE_MAXSIZE = settings.SSE_QUEUE_MAXSIZE
_QUEUE_GET_TIMEOUT_S = settings.SSE_QUEUE_GET_TIMEOUT_S
_STREAM_IDLE_TIMEOUT_S = settings.SSE_STREAM_IDLE_TIMEOUT_S


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _channel(session_id: str) -> str:
    return f"{REDIS_CHANNEL_PREFIX}{session_id}"


def _get_queue(session_id: str) -> queue.Queue[dict[str, Any]]:
    with _SESSION_LOCK:
        q = _SESSION_QUEUES.get(session_id)
        if q is None:
            q = queue.Queue(maxsize=_QUEUE_MAXSIZE)
            _SESSION_QUEUES[session_id] = q
        return q


def _enqueue_local(session_id: str, item: dict[str, Any]) -> None:
    q = _get_queue(session_id)
    try:
        q.put_nowait(item)
    except queue.Full:
        logger.debug(
            "state_stream_queue_full",
            session_id=session_id,
            state=item.get("state"),
        )


def _redis_publish(session_id: str, item: dict[str, Any]) -> None:
    try:
        from app.redis_client import get_redis

        client = get_redis()
        if client is None:
            return
        client.publish(_channel(session_id), json.dumps(item, ensure_ascii=False))
    except Exception as exc:
        logger.debug("state_stream_redis_publish_failed", error=str(exc))


def _ensure_redis_bridge(session_id: str) -> None:
    """Background Redis → local queue bridge (idempotent per session)."""
    with _SESSION_LOCK:
        existing = _SESSION_BRIDGES.get(session_id)
        if existing is not None and existing.is_alive():
            return

        try:
            from app.redis_client import get_redis

            client = get_redis()
        except Exception:
            client = None
        if client is None or not hasattr(client, "pubsub"):
            return

        def _bridge() -> None:
            pubsub = None
            try:
                pubsub = client.pubsub(ignore_subscribe_messages=True)
                pubsub.subscribe(_channel(session_id))
                for message in pubsub.listen():
                    if message is None or message.get("type") != "message":
                        continue
                    raw = message.get("data")
                    if not raw:
                        continue
                    try:
                        item = json.loads(raw)
                    except (TypeError, json.JSONDecodeError):
                        continue
                    if not isinstance(item, dict):
                        continue
                    # Same-process emit already enqueued locally — skip echo.
                    if item.get("origin") == _PROCESS_ORIGIN:
                        continue
                    _enqueue_local(session_id, item)
            except Exception as exc:
                logger.debug("state_stream_redis_bridge_stopped", error=str(exc))
            finally:
                try:
                    if pubsub is not None:
                        pubsub.close()
                except Exception:
                    pass
                with _SESSION_LOCK:
                    if _SESSION_BRIDGES.get(session_id) is threading.current_thread():
                        _SESSION_BRIDGES.pop(session_id, None)

        thread = threading.Thread(
            target=_bridge,
            name=f"sse-bridge-{session_id[:12]}",
            daemon=True,
        )
        _SESSION_BRIDGES[session_id] = thread
        thread.start()


def _format_sse_payload(payload: dict[str, Any]) -> str:
    public = {
        "state": payload.get("state"),
        "label": payload.get("label"),
        "timestamp": payload.get("timestamp"),
    }
    return f"data: {json.dumps(public, ensure_ascii=False)}\n\n"


def emit(session_id: str, state: str, detail: str | None = None) -> None:
    """
    Push one SSE event for a real state transition.

    ``detail`` overrides the pre-approved label when provided; otherwise
    ``STATE_LABELS[state]`` is used so raw internal names never reach the UI.
    """
    if not session_id:
        return

    label = detail if detail is not None else STATE_LABELS.get(state, "Working on your request…")
    event = {
        "state": state,
        "label": label,
        "timestamp": _utc_now_iso(),
        "origin": _PROCESS_ORIGIN,
    }
    _enqueue_local(session_id, event)
    _redis_publish(session_id, event)

    if state == "RESPOND":
        sentinel = {"_sentinel": STREAM_DONE_SENTINEL, "origin": _PROCESS_ORIGIN}
        _enqueue_local(session_id, sentinel)
        _redis_publish(session_id, sentinel)


def _iter_events(session_id: str, *, max_idle_s: float = _STREAM_IDLE_TIMEOUT_S) -> Iterator[str]:
    """Blocking SSE chunk generator (used in tests and async wrapper)."""
    _ensure_redis_bridge(session_id)
    q = _get_queue(session_id)
    idle = 0.0
    while idle < max_idle_s:
        try:
            item = q.get(timeout=_QUEUE_GET_TIMEOUT_S)
        except queue.Empty:
            idle += _QUEUE_GET_TIMEOUT_S
            yield ": keepalive\n\n"
            continue

        idle = 0.0
        if item.get("_sentinel") == STREAM_DONE_SENTINEL:
            break
        yield _format_sse_payload(item)

    if idle >= max_idle_s:
        logger.warning("state_stream_idle_timeout", session_id=session_id)


def stream(session_id: str) -> Iterator[str]:
    """
    Synchronous SSE event generator for ``StreamingResponse``.

    Yields ``data: {state, label, timestamp}\\n\\n`` frames; terminates after
    the RESPOND-stage ``STREAM_DONE_SENTINEL`` is consumed.
    """
    yield from _iter_events(session_id)


async def async_stream(session_id: str, request: Any) -> AsyncIterator[str]:
    """
    Async SSE generator with client-disconnect detection.

    On disconnect, stops yielding immediately; ``emit()`` / ``loop.run()`` are
    unaffected and continue server-side.
    """
    _ensure_redis_bridge(session_id)
    loop = asyncio.get_running_loop()
    idle = 0.0

    while idle < _STREAM_IDLE_TIMEOUT_S:
        if await request.is_disconnected():
            logger.info("state_stream_client_disconnected", session_id=session_id)
            break

        try:
            item = await loop.run_in_executor(
                None,
                lambda: _get_queue(session_id).get(timeout=_QUEUE_GET_TIMEOUT_S),
            )
        except queue.Empty:
            idle += _QUEUE_GET_TIMEOUT_S
            yield ": keepalive\n\n"
            continue

        idle = 0.0
        if item.get("_sentinel") == STREAM_DONE_SENTINEL:
            break
        yield _format_sse_payload(item)

    if idle >= _STREAM_IDLE_TIMEOUT_S:
        logger.warning("state_stream_idle_timeout", session_id=session_id)


def reset_session(session_id: str) -> None:
    """Test helper — drop queued events for a session."""
    with _SESSION_LOCK:
        _SESSION_QUEUES.pop(session_id, None)
        _SESSION_BRIDGES.pop(session_id, None)
