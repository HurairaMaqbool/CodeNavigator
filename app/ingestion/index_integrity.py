# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""
app/ingestion/index_integrity.py
--------------------------------
Single source of truth for vector-index vs metadata consistency.

All readiness, /eval/health, and post-ingest gates MUST use this module so
stale metadata cannot mark a repo "synced" while Chroma is empty or partial.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.observability.logging_config import logger


@dataclass(frozen=True)
class IndexIntegrityReport:
    ok: bool
    chroma_chunks: int
    chroma_files: int
    metadata_chunks: int | None = None
    asset_repo_id: str = ""
    job_id: str | None = None
    mismatch: bool = False
    errors: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "chroma_chunks": self.chroma_chunks,
            "chroma_file_count": self.chroma_files,
            "metadata_chunks_created": self.metadata_chunks,
            "asset_repo_id": self.asset_repo_id,
            "job_id": self.job_id,
            "mismatch": self.mismatch,
            "errors": list(self.errors),
            **self.details,
        }


def chroma_chunk_count(*repo_ids: str | None) -> int:
    """Fast path: max ``col.count()`` across ids (no metadata scan)."""
    best = 0
    try:
        from app.retrieval.vector_store import get_collection

        for rid in repo_ids:
            if not rid:
                continue
            col = get_collection(rid)
            if col is None:
                continue
            best = max(best, col.count())
    except Exception as exc:
        logger.debug("index_integrity_chroma_count_failed", error=str(exc))
    return best


def chroma_counts(*repo_ids: str | None) -> tuple[int, int]:
    """Return (unique_files, chunk_count) from the largest Chroma collection among ids."""
    best_chunks = 0
    best_files = 0
    winning_rid: str | None = None
    try:
        from app.retrieval.vector_store import get_collection

        for rid in repo_ids:
            if not rid:
                continue
            col = get_collection(rid)
            if col is None:
                continue
            cnt = col.count()
            if cnt <= best_chunks:
                continue
            files = 0
            payload = col.get(include=["metadatas"])
            raw_metas = payload.get("metadatas") or []
            metas = raw_metas[0] if raw_metas and isinstance(raw_metas[0], list) else raw_metas
            paths = {
                m.get("file_path") or m.get("display_path")
                for m in metas
                if isinstance(m, dict) and (m.get("file_path") or m.get("display_path"))
            }
            best_chunks = cnt
            best_files = len(paths)
            winning_rid = rid
    except Exception as exc:
        logger.debug("index_integrity_chroma_read_failed", error=str(exc))
    return best_files, best_chunks if winning_rid else 0


def bm25_chunk_count(asset_repo_id: str) -> int:
    """Return number of chunks in the on-disk BM25 index, or 0 if missing."""
    from app.retrieval.bm25_store import load_bm25_index

    loaded = load_bm25_index(asset_repo_id)
    if not loaded:
        return 0
    _bm25, records = loaded
    return len(records) if records else 0


def check_bm25_integrity(
    asset_repo_id: str,
    *,
    expected_chunks: int,
) -> list[str]:
    """Verify BM25 index exists and matches expected chunk count."""
    from app.retrieval.bm25_store import _index_path_for

    errors: list[str] = []
    pkl = _index_path_for(asset_repo_id)
    if not pkl.exists():
        errors.append(f"BM25 index missing at {pkl}")
        return errors
    count = bm25_chunk_count(asset_repo_id)
    if count != expected_chunks:
        errors.append(
            f"BM25 index has {count} chunks but expected {expected_chunks} "
            f"for {asset_repo_id[:12]}..."
        )
    return errors


def check_index_integrity(
    asset_repo_id: str,
    *,
    job_id: str | None = None,
    metadata_chunks: int | None = None,
    expected_chunks: int | None = None,
    min_chunks: int = 50,
) -> IndexIntegrityReport:
    """
    Verify live Chroma state against metadata / expected ingest counts.

    ``expected_chunks`` is used post-ingest (must match Chroma within tolerance).
    ``metadata_chunks`` is used for readiness (detect stale metadata).
    """
    errors: list[str] = []
    chroma_files, chroma_chunks = chroma_counts(asset_repo_id, job_id)
    mismatch = False

    reference = expected_chunks if expected_chunks is not None else metadata_chunks
    if reference is not None and chroma_chunks > 0 and reference != chroma_chunks:
        mismatch = True
        errors.append(
            f"Index integrity violation: Chroma has {chroma_chunks} chunks but "
            f"{'expected' if expected_chunks is not None else 'metadata reports'} "
            f"{reference} for {asset_repo_id[:12]}..."
        )

    if chroma_chunks < min_chunks:
        if metadata_chunks is not None and metadata_chunks > chroma_chunks:
            errors.append(
                f"Vector store has {chroma_chunks} chunks for {asset_repo_id[:12]}... "
                f"but metadata reports {metadata_chunks}. "
                "Re-ingest with force_reindex=true."
            )
        else:
            errors.append(
                f"Chroma collection for {asset_repo_id[:12]}... has {chroma_chunks} chunks "
                f"(minimum {min_chunks}). Re-ingest may be incomplete."
            )

    if mismatch and not any("integrity violation" in e for e in errors):
        errors.insert(0, errors[0] if errors else "metadata/chroma mismatch")

    return IndexIntegrityReport(
        ok=len(errors) == 0,
        chroma_chunks=chroma_chunks,
        chroma_files=chroma_files,
        metadata_chunks=metadata_chunks,
        asset_repo_id=asset_repo_id,
        job_id=job_id,
        mismatch=mismatch,
        errors=errors,
    )


def assert_post_ingest_integrity(
    asset_repo_id: str,
    *,
    job_id: str | None,
    expected_chunks: int,
    min_chunks: int = 1,
) -> IndexIntegrityReport:
    """
    Hard gate after store_chunks — raises if vectors were not persisted correctly.
    Prevents marking a repo synced when Chroma write silently failed.
    """
    report = check_index_integrity(
        asset_repo_id,
        job_id=job_id,
        expected_chunks=expected_chunks,
        min_chunks=min_chunks,
    )
    bm25_errors = check_bm25_integrity(asset_repo_id, expected_chunks=expected_chunks)
    if bm25_errors:
        report = IndexIntegrityReport(
            ok=False,
            chroma_chunks=report.chroma_chunks,
            chroma_files=report.chroma_files,
            metadata_chunks=report.metadata_chunks,
            asset_repo_id=report.asset_repo_id,
            job_id=report.job_id,
            mismatch=report.mismatch,
            errors=[*report.errors, *bm25_errors],
            details={**report.details, "bm25_chunks": bm25_chunk_count(asset_repo_id)},
        )
    if not report.ok:
        logger.critical(
            "post_ingest_integrity_failed",
            asset_repo_id=asset_repo_id,
            job_id=job_id,
            expected=expected_chunks,
            chroma=report.chroma_chunks,
            errors=report.errors,
        )
        raise RuntimeError("; ".join(report.errors))
    return report
