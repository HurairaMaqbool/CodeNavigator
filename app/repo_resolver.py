# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/repo_resolver.py
--------------------
Single source of truth for job_id → asset_repo_id (clone id) resolution.

Every pipeline that reads vectors, BM25, graph, or clone files MUST use this
module — not raw job_id from eval datasets or UI forms.
"""
from __future__ import annotations

from typing import Any

from app.ingestion.metadata_store import metadata_store as _default_store


def resolve_asset_repo_id(
    job_or_asset_id: str,
    *,
    store: Any | None = None,
) -> tuple[Any, str]:
    """
    Resolve a job id or asset id to (metadata, asset_repo_id).

    Vectors, BM25, graph, and clone paths are keyed by asset_repo_id after
    ingestion completes and alias.json is written.

    Pass ``store`` when calling from tests or API layers that patch metadata_store.
    """
    ms = store if store is not None else _default_store
    job_id = job_or_asset_id
    meta = ms.get(job_id)
    asset_repo_id = ms.get_alias(job_id) or job_id
    if (not meta or meta.sync_status != "synced") and asset_repo_id != job_id:
        real_meta = ms.get(asset_repo_id)
        if real_meta:
            meta = real_meta
    return meta, asset_repo_id


def require_synced_repo(
    job_or_asset_id: str,
    *,
    store: Any | None = None,
) -> tuple[Any, str]:
    """Like resolve_asset_repo_id but raises if repo is missing or not synced."""
    meta, asset_repo_id = resolve_asset_repo_id(job_or_asset_id, store=store)
    if not meta or meta.sync_status != "synced":
        status = getattr(meta, "sync_status", "missing")
        raise ValueError(
            f"Repository {job_or_asset_id[:16]}... is not ready (status={status}). "
            "Complete ingestion before chat, eval, or golden CI."
        )
    return meta, asset_repo_id
