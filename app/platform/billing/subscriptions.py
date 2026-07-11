# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/platform/billing/subscriptions.py
------------------------------------
Org subscription state (PostgreSQL or JSON).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.paths import data_path

_SUBS_PATH = data_path("subscriptions.json")


def _use_pg() -> bool:
    from app.platform.db.stores import use_postgres
    return use_postgres()


def _load() -> dict[str, Any]:
    if not _SUBS_PATH.exists():
        return {"orgs": {}}
    try:
        return json.loads(_SUBS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"orgs": {}}


def _save(data: dict[str, Any]) -> None:
    _SUBS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SUBS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_subscription(org_id: str) -> dict[str, Any]:
    if _use_pg():
        from app.platform.db.stores import pg_get_subscription
        return pg_get_subscription(org_id)
    orgs = _load().get("orgs") or {}
    sub = orgs.get(org_id) or {}
    return {
        "org_id": org_id,
        "plan_id": sub.get("plan_id", "free"),
        "status": sub.get("status", "active"),
        "stripe_customer_id": sub.get("stripe_customer_id"),
        "stripe_subscription_id": sub.get("stripe_subscription_id"),
        "updated_at": sub.get("updated_at"),
    }


def set_subscription(
    org_id: str,
    *,
    plan_id: str | None = None,
    status: str | None = None,
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
) -> dict[str, Any]:
    if _use_pg():
        from app.platform.db.stores import pg_set_subscription
        pg_set_subscription(
            org_id,
            plan_id=plan_id,
            status=status,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
        )
        return get_subscription(org_id)
    data = _load()
    orgs = data.setdefault("orgs", {})
    current = dict(orgs.get(org_id) or {})
    if plan_id is not None:
        current["plan_id"] = plan_id
    if status is not None:
        current["status"] = status
    if stripe_customer_id is not None:
        current["stripe_customer_id"] = stripe_customer_id
    if stripe_subscription_id is not None:
        current["stripe_subscription_id"] = stripe_subscription_id
    current["updated_at"] = datetime.now(timezone.utc).isoformat()
    orgs[org_id] = current
    _save(data)
    return get_subscription(org_id)
