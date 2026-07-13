# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""
app/platform/repo_registry.py
-----------------------------
Org-scoped repository listing for Platform admin (GDPR export/purge UI).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import settings
from app.ingestion.metadata_store import metadata_store


def list_tenant_repositories(org_id: str) -> list[dict[str, Any]]:
    """Return repositories belonging to ``org_id``, newest sync first."""
    from app.ingestion.index_integrity import chroma_chunk_count

    repos_root = Path(settings.REPOS_PATH)
    if not repos_root.is_dir():
        return []

    rows: list[dict[str, Any]] = []
    seen = set()
    for meta_path in repos_root.glob("*/metadata.json"):
        repo_id = meta_path.parent.name
        
        # Filter out debug, test, and temporary repositories
        if repo_id.startswith(("test_", "debug_", "audit-", "stale_", "concurrent_", "empty_", "repo-", "_tmp_")):
            continue
        if repo_id in ("test-repo", "debug_repo", "shared-repo", "empty-repo"):
            continue

        meta = metadata_store.get(repo_id)
        if meta is None:
            continue
        record_org = getattr(meta, "org_id", None) or "default"
        if record_org != org_id:
            continue

        # Deduplicate repositories by (repo_url, ref) to prevent duplicate entries rendering
        repo_key = (meta.repo_url, meta.ref)
        if repo_key in seen:
            continue
        seen.add(repo_key)
        asset_repo_id = metadata_store.get_alias(repo_id) or repo_id
        chroma_chunks = chroma_chunk_count(asset_repo_id, repo_id)
        meta_chunks = meta.chunks_created
        integrity_ok = (
            meta.sync_status != "synced"
            or meta_chunks is None
            or chroma_chunks == meta_chunks
        )
        rows.append(
            {
                "repo_id": repo_id,
                "asset_repo_id": asset_repo_id,
                "repo_url": meta.repo_url,
                "ref": meta.ref,
                "sync_status": meta.sync_status,
                "chunks_created": meta.chunks_created,
                "files_parsed": meta.files_parsed,
                "commit_hash": meta.commit_hash,
                "chroma_chunks": chroma_chunks,
                "index_integrity_ok": integrity_ok,
            }
        )

    rows.sort(key=lambda r: (r.get("sync_status") != "synced", r.get("repo_url") or ""))
    return rows
