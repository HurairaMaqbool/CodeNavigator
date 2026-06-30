"""
app/cache/tool_cache.py
-----------------------
Redis-backed tool result cache with in-process L1 fallback.
"""
from __future__ import annotations

import json
from typing import Any

from app.config import settings
from app.redis_client import get_redis

_REDIS_PREFIX = "tool:"


class ToolCache:
    """Dict-like cache: local memory first, Redis shared layer when available."""

    def __init__(self) -> None:
        self._local: dict[str, Any] = {}

    def __contains__(self, key: str) -> bool:
        if key in self._local:
            return True
        client = get_redis()
        if client is None:
            return False
        try:
            return bool(client.exists(f"{_REDIS_PREFIX}{key}"))
        except Exception:
            return False

    def __getitem__(self, key: str) -> Any:
        if key in self._local:
            return self._local[key]
        client = get_redis()
        if client is not None:
            try:
                raw = client.get(f"{_REDIS_PREFIX}{key}")
                if raw:
                    value = json.loads(raw)
                    self._local[key] = value
                    return value
            except Exception:
                pass
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        self._local[key] = value
        client = get_redis()
        if client is None:
            return
        try:
            client.setex(
                f"{_REDIS_PREFIX}{key}",
                settings.REDIS_TOOL_CACHE_TTL_SECONDS,
                json.dumps(value, default=str),
            )
        except Exception:
            pass

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def clear(self) -> None:
        """Reset local cache (tests and per-request isolation)."""
        self._local.clear()
