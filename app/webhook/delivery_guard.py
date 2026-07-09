# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/webhook/delivery_guard.py
-----------------------------
Idempotent GitHub webhook delivery tracking (Redis + in-memory fallback).
"""
from __future__ import annotations

import threading
import time
from typing import Any

from app.config import settings
from app.redis_client import get_redis

_MEMORY: dict[str, float] = {}
_LOCK = threading.Lock()
_REDIS_PREFIX = "webhook:delivery:"


def _prune_memory(now: float) -> None:
    ttl = settings.WEBHOOK_DELIVERY_TTL_SECONDS
    stale = [k for k, ts in _MEMORY.items() if now - ts > ttl]
    for k in stale:
        del _MEMORY[k]


def is_duplicate_delivery(delivery_id: str | None) -> bool:
    """
    Return True if this delivery id was already processed.

    Uses Redis SET NX when available; otherwise an in-process dict.
    """
    if not delivery_id or not delivery_id.strip():
        return False

    delivery_id = delivery_id.strip()
    client = get_redis()
    if client is not None:
        try:
            created = client.set(
                f"{_REDIS_PREFIX}{delivery_id}",
                "1",
                nx=True,
                ex=settings.WEBHOOK_DELIVERY_TTL_SECONDS,
            )
            return not bool(created)
        except Exception:
            pass

    now = time.time()
    with _LOCK:
        _prune_memory(now)
        if delivery_id in _MEMORY:
            return True
        _MEMORY[delivery_id] = now
        return False


def reset_delivery_guard() -> None:
    """Clear in-memory dedup state (tests)."""
    with _LOCK:
        _MEMORY.clear()
