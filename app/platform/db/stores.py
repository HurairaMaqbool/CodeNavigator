# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/platform/db/stores.py
-------------------------
PostgreSQL implementations for platform persistence.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.platform.db.connection import db_cursor, postgres_enabled


def ensure_org(org_id: str) -> None:
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO organizations (org_id, name, plan_id)
            VALUES (%s, %s, 'free')
            ON CONFLICT (org_id) DO NOTHING
            """,
            (org_id, org_id),
        )


# ── API keys ─────────────────────────────────────────────────────────────────

def pg_resolve_api_key(raw_key: str) -> dict[str, Any] | None:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT org_id, label, key_id FROM api_keys
            WHERE key_id = %s AND active = TRUE
            """,
            (raw_key,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {"org_id": row[0], "label": row[1], "key_id": row[2][:12]}


def pg_create_api_key(org_id: str, label: str, key_id: str) -> None:
    ensure_org(org_id)
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO api_keys (key_id, org_id, label, active, created_at)
            VALUES (%s, %s, %s, TRUE, NOW())
            """,
            (key_id, org_id, label),
        )


def pg_list_api_keys(org_id: str | None = None) -> list[dict[str, Any]]:
    with db_cursor() as cur:
        if org_id:
            cur.execute(
                """
                SELECT key_id, org_id, label, active, created_at
                FROM api_keys WHERE org_id = %s ORDER BY created_at DESC
                """,
                (org_id,),
            )
        else:
            cur.execute(
                "SELECT key_id, org_id, label, active, created_at FROM api_keys ORDER BY created_at DESC"
            )
        rows = cur.fetchall()
    return [
        {
            "key_prefix": r[0][:8] + "…",
            "org_id": r[1],
            "label": r[2],
            "active": r[3],
            "created_at": r[4].isoformat() if r[4] else None,
        }
        for r in rows
    ]


def pg_revoke_api_key(org_id: str, key_prefix: str) -> bool:
    with db_cursor() as cur:
        cur.execute(
            """
            UPDATE api_keys SET active = FALSE
            WHERE org_id = %s AND key_id LIKE %s AND active = TRUE
            """,
            (org_id, key_prefix.replace("…", "") + "%"),
        )
        return cur.rowcount > 0


# ── Usage ────────────────────────────────────────────────────────────────────

def pg_increment_usage(org_id: str, month_key: str, metric: str, amount: int = 1) -> dict[str, int]:
    ensure_org(org_id)
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO usage_monthly (org_id, month_key, metric, count)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (org_id, month_key, metric)
            DO UPDATE SET count = usage_monthly.count + EXCLUDED.count
            RETURNING count
            """,
            (org_id, month_key, metric, amount),
        )
        row = cur.fetchone()
        cur.execute(
            """
            SELECT metric, count FROM usage_monthly
            WHERE org_id = %s AND month_key = %s
            """,
            (org_id, month_key),
        )
        return {r[0]: int(r[1]) for r in cur.fetchall()}


def pg_get_usage(org_id: str, month_key: str) -> dict[str, int]:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT metric, count FROM usage_monthly
            WHERE org_id = %s AND month_key = %s
            """,
            (org_id, month_key),
        )
        return {r[0]: int(r[1]) for r in cur.fetchall()}


# ── Subscriptions ────────────────────────────────────────────────────────────

def pg_get_subscription(org_id: str) -> dict[str, Any]:
    ensure_org(org_id)
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT org_id, plan_id, status, stripe_customer_id, stripe_subscription_id, updated_at
            FROM organizations WHERE org_id = %s
            """,
            (org_id,),
        )
        row = cur.fetchone()
    if not row:
        return {"org_id": org_id, "plan_id": "free", "status": "active"}
    return {
        "org_id": row[0],
        "plan_id": row[1] or "free",
        "status": row[2] or "active",
        "stripe_customer_id": row[3],
        "stripe_subscription_id": row[4],
        "updated_at": row[5].isoformat() if row[5] else datetime.now(timezone.utc).isoformat(),
    }


def pg_set_subscription(
    org_id: str,
    *,
    plan_id: str | None = None,
    status: str | None = None,
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
) -> dict[str, Any]:
    ensure_org(org_id)
    updates: list[str] = []
    params: list[Any] = []
    if plan_id is not None:
        updates.append("plan_id = %s")
        params.append(plan_id)
    if status is not None:
        updates.append("status = %s")
        params.append(status)
    if stripe_customer_id is not None:
        updates.append("stripe_customer_id = %s")
        params.append(stripe_customer_id)
    if stripe_subscription_id is not None:
        updates.append("stripe_subscription_id = %s")
        params.append(stripe_subscription_id)
    if updates:
        updates.append("updated_at = NOW()")
        params.append(org_id)
        with db_cursor() as cur:
            cur.execute(
                f"UPDATE organizations SET {', '.join(updates)} WHERE org_id = %s",
                params,
            )
    return pg_get_subscription(org_id)


# ── Audit ────────────────────────────────────────────────────────────────────

def pg_record_audit(
    action: str,
    *,
    org_id: str,
    actor: str,
    resource_type: str,
    resource_id: str,
    details: dict[str, Any],
) -> None:
    ensure_org(org_id)
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit_events (org_id, action, actor, resource_type, resource_id, details)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            """,
            (org_id, action, actor, resource_type, resource_id, json.dumps(details)),
        )


def pg_read_audit(org_id: str | None, limit: int) -> list[dict[str, Any]]:
    with db_cursor() as cur:
        if org_id:
            cur.execute(
                """
                SELECT created_at, action, org_id, actor, resource_type, resource_id, details
                FROM audit_events WHERE org_id = %s
                ORDER BY created_at DESC LIMIT %s
                """,
                (org_id, limit),
            )
        else:
            cur.execute(
                """
                SELECT created_at, action, org_id, actor, resource_type, resource_id, details
                FROM audit_events ORDER BY created_at DESC LIMIT %s
                """,
                (limit,),
            )
        rows = cur.fetchall()
    out = []
    for r in reversed(rows):
        out.append({
            "timestamp": r[0].isoformat() if r[0] else "",
            "action": r[1],
            "org_id": r[2],
            "actor": r[3] or "",
            "resource_type": r[4] or "",
            "resource_id": r[5] or "",
            "details": r[6] if isinstance(r[6], dict) else {},
        })
    return out


def use_postgres() -> bool:
    return postgres_enabled()
