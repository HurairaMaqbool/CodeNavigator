# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/api/status_router.py
------------------------
Public status page data (SLA-lite / uptime transparency).

Does not expose whether optional integrations (Stripe, OIDC, GitHub App)
are configured — that is internal operational detail.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

from app.config import settings

router = APIRouter(prefix="/status", tags=["status"])


@router.get("/public")
def public_status() -> dict[str, Any]:
    """Unauthenticated service health for customers and status pages."""
    from app.platform.db.postgres import check_connection as pg_ok
    from app.platform.db.connection import postgres_enabled
    from app.redis_client import ping_redis

    chroma_ok = False
    try:
        from app.retrieval.vector_store import _get_client

        _get_client()
        chroma_ok = True
    except Exception:
        chroma_ok = False

    redis_ok = ping_redis()
    if postgres_enabled():
        postgres_state = "operational" if pg_ok() else "degraded"
    else:
        postgres_state = "optional_unavailable"

    components = {
        "api": "operational",
        "chroma": "operational" if chroma_ok else "degraded",
        "redis": "operational" if redis_ok else "optional_unavailable",
        "postgres": postgres_state,
    }
    degraded = any(v == "degraded" for v in components.values())
    env = (settings.ENVIRONMENT or "development").lower()
    return {
        "service": "CodeNavigator",
        "version": "2.0.0",
        # Only expose coarse environment class — not internal feature flags.
        "environment": "production" if env == "production" else "non_production",
        "overall": "degraded" if degraded else "operational",
        "components": components,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
