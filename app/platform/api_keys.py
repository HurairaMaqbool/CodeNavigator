# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/platform/api_keys.py
------------------------
Multi-tenant API key registry (PostgreSQL or JSON + legacy settings.API_KEY).
"""
from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings

from app.paths import data_path

_KEYS_PATH = data_path("api_keys.json")
_WEAK_KEYS = frozenset({"", "dev-secret-key", "changeme", "test"})


@dataclass(frozen=True)
class ApiKeyContext:
    org_id: str
    label: str
    key_id: str


def _use_pg() -> bool:
    from app.platform.db.stores import use_postgres
    return use_postgres()


def _load_registry() -> dict[str, Any]:
    if not _KEYS_PATH.exists():
        return {"keys": {}}
    try:
        return json.loads(_KEYS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"keys": {}}


def _save_registry(data: dict[str, Any]) -> None:
    _KEYS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _KEYS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def resolve_api_key(raw_key: str) -> ApiKeyContext | None:
    if not raw_key:
        return None
    if secrets.compare_digest(raw_key, settings.API_KEY):
        return ApiKeyContext(org_id="default", label="primary", key_id="legacy")

    if _use_pg():
        from app.platform.db.stores import pg_resolve_api_key
        meta = pg_resolve_api_key(raw_key)
        if meta:
            return ApiKeyContext(
                org_id=meta["org_id"],
                label=meta["label"],
                key_id=meta["key_id"],
            )
        return None

    registry = _load_registry().get("keys") or {}
    for key_id, meta in registry.items():
        if meta.get("active", True) and secrets.compare_digest(key_id, raw_key):
            return ApiKeyContext(
                org_id=meta.get("org_id", "default"),
                label=meta.get("label", key_id[:8]),
                key_id=key_id[:12],
            )
    return None


def create_api_key(org_id: str, label: str) -> str:
    new_key = secrets.token_urlsafe(32)
    if _use_pg():
        from app.platform.db.stores import pg_create_api_key
        pg_create_api_key(org_id, label, new_key)
        return new_key
    data = _load_registry()
    keys = data.setdefault("keys", {})
    keys[new_key] = {
        "org_id": org_id,
        "label": label,
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_registry(data)
    return new_key


def list_keys(org_id: str | None = None) -> list[dict[str, Any]]:
    if _use_pg():
        from app.platform.db.stores import pg_list_api_keys
        return pg_list_api_keys(org_id)
    out: list[dict[str, Any]] = []
    for key_id, meta in (_load_registry().get("keys") or {}).items():
        if org_id and meta.get("org_id") != org_id:
            continue
        out.append({
            "key_prefix": key_id[:8] + "…",
            "org_id": meta.get("org_id"),
            "label": meta.get("label"),
            "active": meta.get("active", True),
            "created_at": meta.get("created_at"),
        })
    return out


def revoke_api_key(org_id: str, key_prefix: str) -> bool:
    if _use_pg():
        from app.platform.db.stores import pg_revoke_api_key
        return pg_revoke_api_key(org_id, key_prefix)
    data = _load_registry()
    keys = data.get("keys") or {}
    prefix = key_prefix.replace("…", "")
    revoked = False
    for key_id, meta in list(keys.items()):
        if meta.get("org_id") == org_id and key_id.startswith(prefix) and meta.get("active", True):
            meta["active"] = False
            revoked = True
    if revoked:
        _save_registry(data)
    return revoked


def is_production_api_key_valid() -> bool:
    key = (settings.API_KEY or "").strip()
    if key in _WEAK_KEYS or len(key) < 24:
        return False
    return True
