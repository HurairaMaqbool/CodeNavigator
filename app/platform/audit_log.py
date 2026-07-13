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

from app.paths import data_path

_AUDIT_PATH = data_path("audit_log.jsonl")


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
    correlation_id: str | None = None,
) -> None:
    corr = correlation_id or _current_correlation_id()
    if _use_pg():
        from app.platform.db.stores import pg_record_audit
        pg_record_audit(
            action,
            org_id=org_id,
            actor=actor,
            resource_type=resource_type,
            resource_id=resource_id,
            details={**(details or {}), **({"correlation_id": corr} if corr else {})},
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
    if corr:
        entry["correlation_id"] = corr
    _AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _AUDIT_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, default=str) + "\n")


def _current_correlation_id() -> str:
    try:
        import structlog

        return str(structlog.contextvars.get_contextvars().get("request_id") or "")
    except Exception:
        return ""


def _read_tail_lines(path: Path, max_lines: int) -> list[str]:
    """Read up to ``max_lines`` non-empty lines from the end of a file."""
    if not path.exists() or max_lines <= 0:
        return []
    chunk_size = 8192
    data = b""
    with path.open("rb") as fh:
        fh.seek(0, 2)
        pos = fh.tell()
        while pos > 0 and data.count(b"\n") <= max_lines:
            read_size = min(chunk_size, pos)
            pos -= read_size
            fh.seek(pos)
            data = fh.read(read_size) + data
    lines = [ln.decode("utf-8", errors="replace") for ln in data.splitlines() if ln.strip()]
    return lines[-max_lines:]


import re

def _mask_url(val: Any) -> Any:
    if isinstance(val, str):
        # Mask git credentials in URL (e.g. https://token@github.com/... or https://user:pass@github.com/...)
        val = re.sub(r'(https?://)([^@/]+)(@)', r'\1***:***\3', val)
    return val


def _sanitize_event(ev: dict[str, Any]) -> dict[str, Any]:
    if not ev:
        return ev
    ev = dict(ev)
    if "resource_id" in ev:
        ev["resource_id"] = _mask_url(ev["resource_id"])
    if "details" in ev and isinstance(ev["details"], dict):
        details = dict(ev["details"])
        for k, v in details.items():
            details[k] = _mask_url(v)
        ev["details"] = details
    return ev


def read_events(*, org_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    capped = min(limit, 500)
    if _use_pg():
        from app.platform.db.stores import pg_read_audit
        raw_events = pg_read_audit(org_id, capped)
    else:
        if not _AUDIT_PATH.exists():
            return []
        # Scan only the tail — avoids loading multi-MB audit logs on every Platform page load.
        scan_limit = capped * 20 if org_id else capped
        lines = _read_tail_lines(_AUDIT_PATH, scan_limit)
        raw_events = []
        for line in reversed(lines):
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if org_id and ev.get("org_id") != org_id:
                continue
            raw_events.append(ev)
            if len(raw_events) >= capped:
                break
        raw_events = list(reversed(raw_events))

    return [_sanitize_event(ev) for ev in raw_events]
