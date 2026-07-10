# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Shared files/chunks counters for /status and repo readiness checks."""
from __future__ import annotations

from typing import Any

from app.observability.logging_config import logger


def _safe_int(value: Any) -> int | None:
    return value if isinstance(value, int) else None


def ingest_progress_counts(
    meta: Any,
    asset_repo_id: str,
    *,
    job_id: str | None = None,
) -> tuple[int, int]:
    """Resolve files/chunks from metadata with vector-store fallback on asset or job id."""
    files = _safe_int(getattr(meta, "files_parsed", None)) or _safe_int(
        getattr(meta, "file_count", None)
    )
    chunks = _safe_int(getattr(meta, "chunks_created", None))

    try:
        from app.retrieval.vector_store import get_collection

        for rid in (asset_repo_id, job_id):
            if not rid:
                continue
            col = get_collection(rid)
            if col is None or col.count() <= 0:
                continue
            if not chunks:
                chunks = col.count()
            if not files:
                payload = col.get(include=["metadatas"])
                raw_metas = payload.get("metadatas") or []
                if raw_metas and isinstance(raw_metas[0], list):
                    metas = raw_metas[0]
                else:
                    metas = raw_metas
                paths = {
                    m.get("file_path") or m.get("display_path")
                    for m in metas
                    if isinstance(m, dict)
                    and (m.get("file_path") or m.get("display_path"))
                }
                files = len(paths)
            if files and chunks:
                break
    except Exception as exc:
        logger.debug("progress_count_fallback_failed", error=str(exc))

    return int(files or 0), int(chunks or 0)
