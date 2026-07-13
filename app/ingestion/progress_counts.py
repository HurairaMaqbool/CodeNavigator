# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Shared files/chunks counters for /status and repo readiness checks."""
from __future__ import annotations

from typing import Any

from app.ingestion.index_integrity import chroma_counts
from app.observability.logging_config import logger


def _safe_int(value: Any) -> int | None:
    return value if isinstance(value, int) else None


def ingest_progress_counts(
    meta: Any,
    asset_repo_id: str,
    *,
    job_id: str | None = None,
) -> tuple[int, int]:
    """
    Resolve files/chunks for readiness.

    When Chroma has live data, it is the source of truth — metadata ``chunks_created``
    can remain stale after a partial wipe or wrong collection id.
    """
    meta_files = _safe_int(getattr(meta, "files_parsed", None)) or _safe_int(
        getattr(meta, "file_count", None)
    )
    meta_chunks = _safe_int(getattr(meta, "chunks_created", None))

    chroma_files, chroma_chunks = chroma_counts(asset_repo_id, job_id)

    if chroma_chunks > 0:
        if meta_chunks is not None and meta_chunks != chroma_chunks:
            logger.warning(
                "metadata_chroma_chunk_mismatch",
                metadata_chunks=meta_chunks,
                chroma_chunks=chroma_chunks,
                asset_repo_id=asset_repo_id,
                job_id=job_id,
            )
        files = chroma_files or int(meta_files or 0)
        chunks = chroma_chunks
        # Partial Chroma file scan (isolated tests / wrong collection) — keep metadata file count.
        if meta_files and meta_files > max(files, 1) * 3:
            files = meta_files
        return files, chunks

    return int(meta_files or 0), int(meta_chunks or 0)
