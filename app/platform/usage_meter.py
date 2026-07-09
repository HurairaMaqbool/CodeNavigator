# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/platform/usage_meter.py
---------------------------
Per-organization usage counters for billing and quotas.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings
from app.platform.billing.plans import quota_for_plan
from app.platform.billing.subscriptions import get_subscription

_METER_PATH = Path("data/usage_meter.json")


def _use_pg() -> bool:
    from app.platform.db.stores import use_postgres
    return use_postgres()


def _load() -> dict[str, Any]:
    if not _METER_PATH.exists():
        return {}
    try:
        return json.loads(_METER_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: dict[str, Any]) -> None:
    _METER_PATH.parent.mkdir(parents=True, exist_ok=True)
    _METER_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def increment(org_id: str, metric: str, amount: int = 1) -> dict[str, int]:
    month = _month_key()
    if _use_pg():
        from app.platform.db.stores import pg_increment_usage
        return pg_increment_usage(org_id, month, metric, amount)
    data = _load()
    org = data.setdefault(org_id, {})
    month = _month_key()
    bucket = org.setdefault(month, {})
    bucket[metric] = int(bucket.get(metric, 0)) + amount
    _save(data)
    return dict(bucket)


def get_usage(org_id: str) -> dict[str, Any]:
    month = _month_key()
    if _use_pg():
        from app.platform.db.stores import pg_get_usage
        current = pg_get_usage(org_id, month)
    else:
        data = _load()
        org = data.get(org_id, {})
        current = org.get(month, {})
    sub = get_subscription(org_id)
    plan_id = sub.get("plan_id", "free")
    return {
        "org_id": org_id,
        "month": month,
        "metrics": current,
        "plan_id": plan_id,
        "subscription_status": sub.get("status", "active"),
        "limits": {
            "chat_per_month": _effective_limit(org_id, "chat"),
            "ingest_per_month": _effective_limit(org_id, "ingest"),
            "eval_per_month": _effective_limit(org_id, "eval"),
        },
    }


def _effective_limit(org_id: str, metric: str) -> int:
    """Env quotas override plan tiers; plan limits apply in production only."""
    env_cap = {
        "chat": settings.QUOTA_CHAT_PER_MONTH,
        "ingest": settings.QUOTA_INGEST_PER_MONTH,
        "eval": settings.QUOTA_EVAL_PER_MONTH,
    }.get(metric, 0)
    if env_cap > 0:
        return env_cap
    if settings.ENVIRONMENT.lower() != "production":
        return 0
    sub = get_subscription(org_id)
    return quota_for_plan(sub.get("plan_id", "free"), metric)


def check_quota(org_id: str, metric: str) -> bool:
    """Return True if under quota (or quota disabled)."""
    cap = _effective_limit(org_id, metric)
    if cap <= 0:
        return True
    usage = get_usage(org_id)["metrics"].get(metric, 0)
    return usage < cap
