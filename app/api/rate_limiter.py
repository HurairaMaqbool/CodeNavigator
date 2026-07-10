# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/api/rate_limiter.py
-----------------------
Sliding-window request throttling — Module 5 (Layer 2: API Layer).

Protects free-tier Groq quota from exhaustion.
Keyed by API Key (via ApiKeyContext) to prevent cross-tenant quota theft.

Implementation:
  * In-memory O(1) collections.deque of timestamps.
  * Window duration is fixed to 60 seconds (rate per minute).
  * Limits are read from `settings` dynamically to prevent hardcoding.
  * Note: In a multi-worker deployment, this in-memory deque upgrades to a
    Redis-backed sorted set (ZADD/ZREMRANGEBYSCORE/ZCARD) with the same interface.
"""

from __future__ import annotations

import time
from collections import deque
from fastapi import Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.auth import verify_api_key
from app.config import settings
from app.platform.api_keys import ApiKeyContext

# Legacy slowapi limiter instance preserved to prevent decorator breakage in router.py
limiter = Limiter(key_func=get_remote_address)

# Sliding window storage: mapping (org_id, endpoint) -> deque of timestamps
_rate_limit_store: dict[tuple[str, str], deque[float]] = {}


def check_rate_limit(endpoint: str):
    """
    FastAPI dependency factory for sliding-window rate limiting.

    Usage:
        @router.post("/chat", dependencies=[Depends(check_rate_limit("chat"))])
        def chat_route(...):
            ...
    """
    async def dependency(ctx: ApiKeyContext = Depends(verify_api_key)) -> ApiKeyContext:
        if settings.ENVIRONMENT.lower() in ("development", "testing"):
            return ctx
        org_id = ctx.org_id
        now = time.time()
        window_seconds = 60

        # Read limit from settings or fallback to defaults
        if endpoint == "chat":
            limit = getattr(settings, "RATE_LIMIT_CHAT_PER_MINUTE", 10)
        elif endpoint == "ingest":
            limit = getattr(settings, "RATE_LIMIT_INGEST_PER_MINUTE", 3)
        else:
            limit = getattr(settings, "RATE_LIMIT_DEFAULT_PER_MINUTE", 60)

        store_key = (org_id, endpoint)
        if store_key not in _rate_limit_store:
            _rate_limit_store[store_key] = deque()

        timestamps = _rate_limit_store[store_key]

        # Evict timestamps older than the sliding window from the left
        while timestamps and timestamps[0] < now - window_seconds:
            timestamps.popleft()

        # Check limit
        if len(timestamps) >= limit:
            retry_after = int(window_seconds - (now - timestamps[0]))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "Rate limit exceeded",
                    "error_code": "RATE_LIMIT_EXCEEDED",
                    "message": f"Rate limit exceeded for endpoint '{endpoint}'. Please try again in {retry_after} seconds.",
                    "retry_after": retry_after
                },
                headers={"Retry-After": str(retry_after)}
            )

        timestamps.append(now)
        return ctx

    return dependency
