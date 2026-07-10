# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""
app/ingestion/repo_readiness.py
-------------------------------
Single source of truth for whether a repository is ready for /chat.

Handles job_id ↔ asset_repo_id alias pairs where metadata can diverge
(e.g. job_id synced while asset checkpoint stuck at indexing).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.ingestion.metadata_store import RepoMetadata, Stage, metadata_store
from app.observability.logging_config import logger

_IN_PROGRESS = frozenset({"pending", "cloning", "filtering", "parsing", "indexing"})


@dataclass(frozen=True)
class RepoReadiness:
    ready: bool
    job_id: str
    asset_repo_id: str
    meta: RepoMetadata | None
    block_message: str = ""
    block_reason: str = ""  # indexing | failed | unknown | needs_reindex
    files_parsed: int = 0
    chunks_created: int = 0
    sync_status: str = "unknown"


def _index_counts(
    meta: RepoMetadata | None,
    asset_repo_id: str,
    *,
    job_id: str | None = None,
) -> tuple[int, int]:
    """Return (files, chunks) from metadata with Chroma fallback."""
    from app.ingestion.progress_counts import ingest_progress_counts

    if meta is None:
        meta = RepoMetadata(
            repo_id=asset_repo_id,
            repo_url="",
            ref="HEAD",
            sync_status="unknown",
            schema_version=1,
        )
    return ingest_progress_counts(meta, asset_repo_id, job_id=job_id)


def _meta_int(value: Any) -> int | None:
    return value if isinstance(value, int) else None


def _pick_authoritative_meta(
    job_id: str,
    asset_repo_id: str,
    *,
    store: Any | None = None,
) -> RepoMetadata | None:
    """Prefer synced metadata across job + asset alias pair."""
    ms = store if store is not None else metadata_store
    meta_job = ms.get(job_id)
    meta_asset = ms.get(asset_repo_id) if asset_repo_id != job_id else None

    if meta_job and meta_job.sync_status == "synced":
        return meta_job
    if meta_asset and meta_asset.sync_status == "synced":
        return meta_asset
    if meta_job:
        return meta_job
    return meta_asset


def repair_alias_pair_on_read(job_id: str, *, store: Any | None = None) -> None:
    """If job_id is synced but asset alias is stuck, mirror synced state to asset."""
    ms = store if store is not None else metadata_store
    asset = ms.get_alias(job_id) or job_id
    if asset == job_id:
        return
    job_meta = ms.get(job_id)
    asset_meta = ms.get(asset)
    if (
        job_meta
        and job_meta.sync_status == "synced"
        and asset_meta
        and asset_meta.sync_status != "synced"
    ):
        files, chunks = _index_counts(job_meta, asset, job_id=job_id)
        mirror_sync_to_alias_pair(
            job_id,
            asset,
            commit_hash=job_meta.commit_hash or "",
            cloned_at=job_meta.cloned_at or "",
            files_parsed=files or getattr(job_meta, "files_parsed", 0) or 0,
            chunks_created=chunks or getattr(job_meta, "chunks_created", 0) or 0,
        )


def verify_sync_consistency(
    meta: RepoMetadata | None,
    asset_repo_id: str,
    *,
    job_id: str | None = None,
    auto_repair: bool = True,
) -> tuple[bool, int, int]:
    """
    Enforce: sync_status == synced ⟺ files>0 AND chunks>0 AND no error.

    Returns (is_consistent_or_repaired, files, chunks).
    """
    if meta is None:
        return False, 0, 0

    files, chunks = _index_counts(meta, asset_repo_id, job_id=job_id)
    claimed_synced = meta.sync_status == "synced"
    err = getattr(meta, "error_reason", None)
    has_error = isinstance(err, str) and bool(err.strip())

    if claimed_synced:
        meta_chunks = _meta_int(getattr(meta, "chunks_created", None))
        meta_files = _meta_int(getattr(meta, "files_parsed", None)) or _meta_int(
            getattr(meta, "file_count", None)
        )
        counts_match = (
            (meta_chunks is None or chunks == meta_chunks)
            and (meta_files is None or files == meta_files)
        )
        if files > 0 and chunks > 0 and not has_error and counts_match:
            return True, files, chunks
        logger.critical(
            "sync_consistency_violation",
            repo_id=meta.repo_id,
            asset_repo_id=asset_repo_id,
            sync_status=meta.sync_status,
            files_parsed=files,
            chunks_created=chunks,
            error_reason=meta.error_reason,
        )
        return False, files, chunks

    # Stale indexing with a complete index present — heal only when ingest clearly finished.
    if auto_repair and meta.sync_status in _IN_PROGRESS and chunks > 0 and files > 0:
        raw = metadata_store._read_raw(meta.repo_id) or {}
        progress = str(raw.get("parsing_progress") or "")
        if "Processed" in progress and "/" in progress:
            try:
                tail = progress.split("Processed", 1)[1].strip()
                done_s, rest = tail.split("/", 1)
                total_s = rest.strip().split()[0]
                if int(done_s) < int(total_s):
                    return not claimed_synced, files, chunks
            except (ValueError, IndexError):
                pass

        sibling_synced = False
        if job_id and job_id != meta.repo_id:
            sib = metadata_store.get(job_id)
            sibling_synced = bool(sib and sib.sync_status == "synced")
        else:
            for alias_target in (asset_repo_id, metadata_store.get_alias(meta.repo_id) or ""):
                if not alias_target or alias_target == meta.repo_id:
                    continue
                sib = metadata_store.get(alias_target)
                if sib and sib.sync_status == "synced":
                    sibling_synced = True
                    break

        finished_marker = "complete" in progress.lower()
        if not sibling_synced and not finished_marker:
            return not claimed_synced, files, chunks

        logger.warning(
            "stale_indexing_checkpoint_auto_repair",
            repo_id=meta.repo_id,
            asset_repo_id=asset_repo_id,
            sync_status=meta.sync_status,
            files_parsed=files,
            chunks_created=chunks,
            sibling_synced=sibling_synced,
        )
        try:
            metadata_store.mark_synced(
                meta.repo_id,
                commit_hash=meta.commit_hash or "",
                cloned_at=meta.cloned_at or "",
                files_parsed=files,
                chunks_created=chunks,
            )
            return True, files, chunks
        except Exception as exc:
            logger.error("stale_checkpoint_repair_failed", error=str(exc))

    return not claimed_synced, files, chunks


def mirror_sync_to_alias_pair(
    job_id: str,
    asset_repo_id: str,
    *,
    commit_hash: str,
    cloned_at: str,
    files_parsed: int,
    chunks_created: int,
) -> None:
    """Keep job_id and asset_repo_id metadata aligned after successful ingest."""
    for rid in {job_id, asset_repo_id}:
        try:
            if metadata_store.get(rid) is not None:
                metadata_store.mark_synced(
                    rid,
                    commit_hash=commit_hash,
                    cloned_at=cloned_at,
                    files_parsed=files_parsed,
                    chunks_created=chunks_created,
                )
        except KeyError:
            logger.debug("mirror_sync_skipped_missing_meta", repo_id=rid)


def evaluate_chat_readiness(
    job_id: str,
    *,
    asset_repo_id: str | None = None,
    store: Any | None = None,
) -> RepoReadiness:
    """
    Determine if /chat should proceed for the frontend's job_id.

    ``asset_repo_id`` is where vectors/BM25 live (may differ when ref=HEAD vs main).
    """
    from app.repo_resolver import resolve_asset_repo_id

    ms = store if store is not None else metadata_store
    repair_alias_pair_on_read(job_id, store=ms)
    resolved_meta, resolved_asset = resolve_asset_repo_id(job_id, store=ms)
    asset = asset_repo_id or resolved_asset
    meta = _pick_authoritative_meta(job_id, asset, store=ms) or resolved_meta

    if meta is None:
        return RepoReadiness(
            ready=False,
            job_id=job_id,
            asset_repo_id=asset,
            meta=None,
            block_message="Unknown repository — ingest a GitHub URL first.",
            block_reason="unknown",
        )

    if meta.sync_status == "failed":
        reason = meta.error_reason or "unknown error"
        return RepoReadiness(
            ready=False,
            job_id=job_id,
            asset_repo_id=asset,
            meta=meta,
            block_message=f"Ingestion failed: {reason}. Re-run /ingest to retry.",
            block_reason="failed",
            sync_status="failed",
        )

    consistent, files, chunks = verify_sync_consistency(
        meta, asset, job_id=job_id, auto_repair=True,
    )
    meta = ms.get(meta.repo_id) or meta  # refresh after possible repair

    if meta.sync_status == "synced" and consistent:
        return RepoReadiness(
            ready=True,
            job_id=job_id,
            asset_repo_id=asset,
            meta=meta,
            files_parsed=files,
            chunks_created=chunks,
            sync_status="synced",
        )

    if meta.sync_status in _IN_PROGRESS:
        progress = ""
        raw = metadata_store._read_raw(meta.repo_id)  # noqa: SLF001 — diagnostics only
        if raw and raw.get("parsing_progress"):
            progress = f" ({raw['parsing_progress']})"
        return RepoReadiness(
            ready=False,
            job_id=job_id,
            asset_repo_id=asset,
            meta=meta,
            block_message=(
                f"This repository is still indexing (status: {meta.sync_status}{progress}). "
                f"Progress: {files} files, {chunks} chunks indexed so far. "
                "Please wait for ingestion to complete, then try again."
            ),
            block_reason="indexing",
            files_parsed=files,
            chunks_created=chunks,
            sync_status=meta.sync_status,
        )

    return RepoReadiness(
        ready=False,
        job_id=job_id,
        asset_repo_id=asset,
        meta=meta,
        block_message=(
            f"Repository is not ready (status: {meta.sync_status}). "
            "Re-run /ingest with force_reindex=true if this persists."
        ),
        block_reason="needs_reindex",
        files_parsed=files,
        chunks_created=chunks,
        sync_status=meta.sync_status,
    )


def audit_all_repos_consistency() -> list[dict[str, Any]]:
    """
    Background/on-read safeguard: scan every repo metadata for invariant violations.
    Logs CRITICAL for any mismatch and returns violation records.
    """
    from pathlib import Path

    from app.config import settings

    violations: list[dict[str, Any]] = []
    repos_root = Path(settings.REPOS_PATH)
    if not repos_root.is_dir():
        return violations

    for meta_path in repos_root.glob("*/metadata.json"):
        rid = meta_path.parent.name
        meta = metadata_store.get(rid)
        if meta is None:
            continue
        asset = metadata_store.get_alias(rid) or rid
        consistent, files, chunks = verify_sync_consistency(
            meta, asset, job_id=rid, auto_repair=True,
        )
        if meta.sync_status == "synced" and not consistent:
            record = {
                "repo_id": rid,
                "asset_repo_id": asset,
                "files_parsed": files,
                "chunks_created": chunks,
                "error_reason": meta.error_reason,
            }
            violations.append(record)
            logger.critical("repo_consistency_audit_violation", **record)
    return violations


def status_and_chat_agree(job_id: str, *, store: Any | None = None) -> bool:
    """True when /status ready flag matches /chat gated flag for the same job_id."""
    from app.repo_resolver import resolve_asset_repo_id

    ms = store if store is not None else metadata_store
    _meta, asset = resolve_asset_repo_id(job_id, store=ms)
    readiness = evaluate_chat_readiness(job_id, asset_repo_id=asset)
    status_ready = readiness.ready
    chat_ready = readiness.ready
    return status_ready == chat_ready
