"""
app/api/status_router.py
------------------------
Public status page data (SLA-lite / uptime transparency).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

from app.config import settings

router = APIRouter(prefix="/status", tags=["status"])


@router.get("/public")
def public_status() -> dict[str, Any]:
    """Unauthenticated service status for customers and status pages."""
    from app.platform.db.postgres import check_connection as pg_ok
    from app.platform.db.connection import postgres_enabled
    from app.redis_client import ping_redis

    chroma_ok = False
    try:
        from app.retrieval.vector_store import _get_client
        _get_client()
        chroma_ok = True
    except Exception:
        pass

    components = {
        "api": "operational",
        "chroma": "operational" if chroma_ok else "degraded",
        "redis": "operational" if ping_redis() else "optional_unavailable",
        "postgres": (
            "operational" if postgres_enabled() and pg_ok() else
            "not_configured" if not postgres_enabled() else "degraded"
        ),
        "stripe": "configured" if settings.STRIPE_SECRET_KEY else "not_configured",
        "oidc": "configured" if settings.OIDC_CLIENT_ID else "not_configured",
        "github_app": "configured" if settings.GITHUB_APP_ID else "not_configured",
    }
    degraded = any(v == "degraded" for v in components.values())
    return {
        "service": "CodeNavigator",
        "version": "2.0.0",
        "environment": settings.ENVIRONMENT,
        "overall": "degraded" if degraded else "operational",
        "components": components,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
