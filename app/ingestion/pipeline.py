# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/ingestion/pipeline.py
-------------------------
Synchronous ingestion pipeline — no Celery dependency.

FastAPI BackgroundTasks and verification scripts import from here so ingest
works even when Celery/Redis are not installed (local dev fallback).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.graph.builder import build_graph
from app.ingestion.clone import IngestionError, clone_repo
from app.ingestion.file_filter import filter_repo_files, safe_decode
from app.ingestion.locking import lock_manager
from app.ingestion.metadata_store import Stage, metadata_store
from app.observability.logging_config import logger
from app.parsing.chunker import chunk_all_files
from app.parsing.tree_sitter_parser import parse_file
from app.retrieval.bm25_store import build_bm25_index
from app.retrieval.vector_store import store_chunks


def _mark_failed_safe(
    job_id: str,
    resolved_repo_id: str | None,
    *,
    error_reason: str,
) -> None:
    for repo_id in (job_id, resolved_repo_id):
        if not repo_id:
            continue
        try:
            metadata_store.mark_failed(repo_id, error_reason=error_reason)
            return
        except KeyError:
            continue
    logger.warning(
        "mark_failed_skipped_no_metadata",
        job_id=job_id,
        resolved_repo_id=resolved_repo_id,
    )


def _refresh_golden_set_async(log: Any) -> None:
    import threading

    def _worker() -> None:
        try:
            from eval.golden_runner import run_golden_set

            run_golden_set()
        except Exception as exc:
            log.warning("golden_set_refresh_failed", error=str(exc))

    threading.Thread(target=_worker, daemon=True).start()


def run_ingestion_sync(
    repo_url: str,
    ref: str | None,
    force_reindex: bool,
    job_id: str,
    *,
    clone_res: Any = None,
    prefiltered_files: list[Any] | None = None,
    re_raise: bool = False,
) -> bool:
    """
    Synchronous entry point for the ingestion pipeline.
    Returns True on success. When re_raise is True (Celery), failures propagate.
    """
    log = logger.bind(job_id=job_id, repo_url=repo_url, job="ingest_pipeline")
    log.info("ingest_pipeline_started")
    resolved_repo_id: str | None = None
    try:
        if clone_res is None:
            try:
                clone_res = clone_repo(repo_url, ref)
            except Exception as e:
                raise IngestionError(f"Clone failed: {e}") from e

        resolved_repo_id = clone_res.repo_id
        if clone_res.repo_id != job_id:
            metadata_store.save_alias(job_id, clone_res.repo_id)

        if prefiltered_files is not None:
            files = prefiltered_files
        else:
            files = filter_repo_files(clone_res.clone_path, repo_id=clone_res.repo_id)
        if not files:
            metadata_store.mark_failed(
                job_id,
                error_reason="No supported files found (Python/JS/TS only in v1)",
            )
            return False

        contents: dict[str, str] = {}
        file_records: dict[str, tuple[str, str, str]] = {}
        parsed_files = []

        total_files = len(files)
        for idx, f in enumerate(files):
            text, decode_err = safe_decode(Path(f.path))
            if decode_err or not text:
                continue
            contents[f.display_path] = text
            file_records[f.display_path] = (str(f.path), f.display_path, f.normalized_path)

            parsed = parse_file(str(f.path), text, f.language)
            if parsed:
                parsed.file_path = f.display_path
                parsed_files.append(parsed)

            try:
                metadata_store.update(
                    resolved_repo_id or job_id,
                    Stage.PARSING,
                    progress=f"Processed {idx + 1}/{total_files} files",
                )
            except Exception as meta_exc:
                logger.warning("failed_to_write_parsing_progress_checkpoint", error=str(meta_exc))

        chunks = chunk_all_files(parsed_files, contents, file_records)

        if force_reindex:
            from app.agent.semantic_cache import clear_repo_semantic_cache

            for rid in {clone_res.repo_id, job_id}:
                clear_repo_semantic_cache(rid)
            alias = metadata_store.get_alias(job_id)
            if alias:
                clear_repo_semantic_cache(alias)

        store_chunks(clone_res.repo_id, chunks, force_reindex=force_reindex)
        build_bm25_index(clone_res.repo_id, chunks)

        from app.ingestion.index_integrity import assert_post_ingest_integrity

        assert_post_ingest_integrity(
            clone_res.repo_id,
            job_id=job_id,
            expected_chunks=len(chunks),
            min_chunks=max(1, min(50, len(chunks))),
        )

        build_graph(clone_res.repo_id, parsed_files)

        files_parsed = len(parsed_files) if parsed_files else len(files)
        from app.ingestion.repo_readiness import mirror_sync_to_alias_pair

        mirror_sync_to_alias_pair(
            job_id,
            clone_res.repo_id,
            commit_hash=clone_res.commit_hash,
            cloned_at=getattr(clone_res, "cloned_at", "") or "",
            files_parsed=files_parsed,
            chunks_created=len(chunks),
        )
        log.info("ingest_pipeline_success")
        _refresh_golden_set_async(log)
        return True

    except Exception as e:
        log.exception("ingest_pipeline_failed")
        _mark_failed_safe(job_id, resolved_repo_id, error_reason=str(e))
        if re_raise:
            raise
        return False
    finally:
        lock_manager.release(job_id)
