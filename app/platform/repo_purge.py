# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/platform/repo_purge.py
--------------------------
GDPR-compliant repository purge: clone, vectors, BM25, graph, cache, metadata.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from app.config import settings
from app.ingestion.metadata_store import metadata_store
from app.observability.logging_config import logger
from app.platform.tenant_context import require_org_access
from app.repo_resolver import resolve_asset_repo_id


def _delete_chroma_collections(repo_id: str) -> list[str]:
    deleted: list[str] = []
    try:
        from app.retrieval.vector_store import _get_client, _collection_name_for

        client = _get_client()
        names = [
            _collection_name_for(repo_id),
            f"{repo_id[:50]}_answer_cache",
        ]
        for name in names:
            try:
                client.delete_collection(name)
                deleted.append(name)
            except Exception:
                pass
    except Exception as exc:
        logger.warning("purge_chroma_failed", repo_id=repo_id, error=str(exc))
    return deleted


def _delete_bm25(repo_id: str) -> bool:
    pkl = Path(settings.BM25_INDEX_PATH) / repo_id / "bm25.pkl"
    if pkl.exists():
        try:
            pkl.unlink()
            parent = pkl.parent
            if parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
            return True
        except Exception:
            pass
    return False


def _delete_graph(repo_id: str) -> bool:
    graph_dir = Path(settings.GRAPH_STORE_PATH) / repo_id
    if graph_dir.exists():
        try:
            shutil.rmtree(graph_dir)
            return True
        except Exception:
            pass
    return False


def _delete_repo_dir(repo_id: str) -> bool:
    repo_dir = Path(settings.REPOS_PATH) / repo_id
    if repo_dir.exists():
        try:
            shutil.rmtree(repo_dir)
            return True
        except Exception:
            pass
    return False


def purge_repository(job_or_asset_id: str, *, skip_auth: bool = False) -> dict[str, Any]:
    """
    Delete all persisted data for a repository (job id or asset id).

    Resolves alias so both job folder and asset indexes are removed.
    """
    meta, asset_repo_id = resolve_asset_repo_id(job_or_asset_id)
    if meta and not skip_auth:
        org_id = getattr(meta, "org_id", None) or "default"
        require_org_access(org_id)

    ids_to_purge = {job_or_asset_id, asset_repo_id}
    if meta:
        ids_to_purge.add(meta.repo_id)

    # Follow alias from job id
    alias = metadata_store.get_alias(job_or_asset_id)
    if alias:
        ids_to_purge.add(alias)

    chroma_deleted: list[str] = []
    for rid in ids_to_purge:
        chroma_deleted.extend(_delete_chroma_collections(rid))
        _delete_bm25(rid)
        _delete_graph(rid)
        _delete_repo_dir(rid)

    return {
        "purged_ids": sorted(ids_to_purge),
        "chroma_collections_removed": list(set(chroma_deleted)),
        "status": "purged",
    }


def export_repository_data(job_or_asset_id: str) -> dict[str, Any]:
    """Export metadata snapshot for GDPR data portability."""
    meta, asset_repo_id = resolve_asset_repo_id(job_or_asset_id)
    if meta:
        require_org_access(getattr(meta, "org_id", None) or "default")
    payload: dict[str, Any] = {
        "job_or_asset_id": job_or_asset_id,
        "asset_repo_id": asset_repo_id,
        "metadata": None,
    }
    if meta:
        from dataclasses import asdict
        payload["metadata"] = asdict(meta)
    return payload
