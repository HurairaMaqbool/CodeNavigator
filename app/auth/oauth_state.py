# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/auth/oauth_state.py
-----------------------
OAuth CSRF state storage (Redis with in-memory fallback).
"""
from __future__ import annotations

import secrets
import time

_STATE_TTL = 600
_MEMORY: dict[str, float] = {}


def _redis_key(state: str) -> str:
    return f"oauth:state:{state}"


def create_state() -> str:
    state = secrets.token_urlsafe(24)
    store_state(state)
    return state


def store_state(state: str) -> None:
    from app.redis_client import get_redis

    client = get_redis()
    if client is not None:
        try:
            client.setex(_redis_key(state), _STATE_TTL, "1")
            return
        except Exception:
            pass
    _MEMORY[state] = time.time()


def consume_state(state: str) -> bool:
    """Return True if state was valid (one-time use)."""
    from app.redis_client import get_redis

    client = get_redis()
    if client is not None:
        try:
            key = _redis_key(state)
            if client.delete(key):
                return True
        except Exception:
            pass
    ts = _MEMORY.pop(state, None)
    if ts is None:
        return False
    if time.time() - ts > _STATE_TTL:
        return False
    return True


def clear_memory_states() -> None:
    """Test helper."""
    _MEMORY.clear()
