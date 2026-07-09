# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/integrations/github_app/installations.py
--------------------------------------------
Map GitHub App installations to tenant org_id.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_INSTALL_PATH = Path("data/github_installations.json")


def _load() -> dict[str, Any]:
    if not _INSTALL_PATH.exists():
        return {"installations": {}}
    try:
        return json.loads(_INSTALL_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"installations": {}}


def _save(data: dict[str, Any]) -> None:
    _INSTALL_PATH.parent.mkdir(parents=True, exist_ok=True)
    _INSTALL_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def register_installation(
    installation_id: int,
    *,
    org_id: str,
    account_login: str = "",
    repos: list[str] | None = None,
) -> dict[str, Any]:
    data = _load()
    installs = data.setdefault("installations", {})
    installs[str(installation_id)] = {
        "installation_id": installation_id,
        "org_id": org_id,
        "account_login": account_login,
        "repos": repos or [],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _save(data)
    return installs[str(installation_id)]


def remove_installation(installation_id: int) -> None:
    data = _load()
    installs = data.get("installations") or {}
    installs.pop(str(installation_id), None)
    data["installations"] = installs
    _save(data)


def get_org_for_installation(installation_id: int | None) -> str:
    if installation_id is None:
        return "default"
    rec = (_load().get("installations") or {}).get(str(installation_id))
    if rec:
        return rec.get("org_id", "default")
    return "default"


def get_installation_for_repo(full_name: str) -> int | None:
    """Find installation that has repo full_name (owner/repo)."""
    for rec in (_load().get("installations") or {}).values():
        if full_name in rec.get("repos", []):
            return int(rec["installation_id"])
    return None


def list_installations(org_id: str | None = None) -> list[dict[str, Any]]:
    out = list((_load().get("installations") or {}).values())
    if org_id:
        out = [i for i in out if i.get("org_id") == org_id]
    return out


def add_repo_to_installation(installation_id: int, full_name: str) -> None:
    """Track repo full_name (owner/repo) under an installation for clone auth."""
    data = _load()
    installs = data.get("installations") or {}
    rec = installs.get(str(installation_id))
    if not rec:
        return
    repos: list[str] = list(rec.get("repos") or [])
    if full_name not in repos:
        repos.append(full_name)
        rec["repos"] = repos
        installs[str(installation_id)] = rec
        data["installations"] = installs
        _save(data)
