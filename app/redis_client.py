"""
app/redis_client.py
-------------------
Lazy Redis client with graceful fallback when Redis is unavailable.
"""
from __future__ import annotations

import threading
from typing import Any

from app.config import settings
from app.observability.logging_config import logger

_client: Any = None
_available: bool | None = None
_lock = threading.Lock()


def get_redis() -> Any | None:
    """Return a Redis client or None if disabled/unreachable."""
    global _client, _available

    if not settings.REDIS_ENABLED:
        return None

    with _lock:
        if _available is False:
            return None
        if _client is not None:
            return _client
        try:
            import redis

            _client = redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT_S,
            )
            _client.ping()
            _available = True
            logger.info("redis_connected", url=settings.REDIS_URL.split("@")[-1])
            return _client
        except Exception as exc:
            _available = False
            logger.warning("redis_unavailable", error=str(exc))
            return None


def ping_redis() -> bool:
    client = get_redis()
    if client is None:
        return False
    try:
        return bool(client.ping())
    except Exception:
        return False


def reset_redis_client() -> None:
    """Clear cached client (tests)."""
    global _client, _available
    with _lock:
        _client = None
        _available = None
