# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/platform/audit_log.py
-------------------------
Append-only audit trail (PostgreSQL or JSONL).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_AUDIT_PATH = Path("data/audit_log.jsonl")


def _use_pg() -> bool:
    from app.platform.db.stores import use_postgres
    return use_postgres()


def record_event(
    action: str,
    *,
    org_id: str = "default",
    actor: str = "",
    resource_type: str = "",
    resource_id: str = "",
    details: dict[str, Any] | None = None,
) -> None:
    if _use_pg():
        from app.platform.db.stores import pg_record_audit
        pg_record_audit(
            action,
            org_id=org_id,
            actor=actor,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
        )
        return
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "org_id": org_id,
        "actor": actor,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "details": details or {},
    }
    _AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _AUDIT_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, default=str) + "\n")


def read_events(*, org_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    if _use_pg():
        from app.platform.db.stores import pg_read_audit
        return pg_read_audit(org_id, min(limit, 500))
    if not _AUDIT_PATH.exists():
        return []
    lines = _AUDIT_PATH.read_text(encoding="utf-8").strip().splitlines()
    events: list[dict[str, Any]] = []
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except Exception:
            continue
        if org_id and ev.get("org_id") != org_id:
            continue
        events.append(ev)
        if len(events) >= limit:
            break
    return list(reversed(events))
