# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

from pathlib import Path
from typing import Any
from app.tasks.celery_app import celery_app
from app.observability.logging_config import logger
from app.ingestion.metadata_store import metadata_store
from app.ingestion.locking import lock_manager
from app.ingestion.clone import clone_repo, RepoNotFoundError, PrivateRepoError, NetworkTimeoutError, RepoTooLargeError, IngestionError
from app.ingestion.file_filter import filter_repo_files, safe_decode
from app.parsing.chunker import chunk_all_files
from app.parsing.tree_sitter_parser import parse_file
from app.retrieval.vector_store import store_chunks
from app.retrieval.bm25_store import store_bm25, build_bm25_index
from app.graph.builder import build_graph


def _mark_failed_safe(
    job_id: str,
    resolved_repo_id: str | None,
    *,
    error_reason: str,
) -> None:
    """Mark ingestion failed without masking the original error on missing metadata."""
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
    """
    Re-run the Golden Set CI in a background thread after a successful ingest so
    the dashboard status always reflects the current agent — never a stale,
    days-old result. Best-effort: a failure here must never affect ingestion.
    """
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
    This can be called directly by Celery, or by FastAPI BackgroundTasks.
    When clone_res/prefiltered_files are supplied (API pre-flight), skip re-clone.
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

        # Parse and Chunk
        contents = {}
        file_records = {}
        parsed_files = []

        for f in files:
            text, decode_err = safe_decode(Path(f.path))
            if decode_err or not text:
                continue
            contents[f.display_path] = text
            file_records[f.display_path] = (str(f.path), f.display_path, f.normalized_path)

            parsed = parse_file(str(f.path), text, f.language)
            if parsed:
                parsed.file_path = f.display_path
                parsed_files.append(parsed)

        chunks = chunk_all_files(parsed_files, contents, file_records)

        # Embeddings & Vector Store + BM25
        store_chunks(clone_res.repo_id, chunks, force_reindex=force_reindex)
        build_bm25_index(clone_res.repo_id, chunks)

        # Graph Builder
        build_graph(clone_res.repo_id, parsed_files)

        # Status is keyed by job_id (provisional id from /ingest); vectors/graph use resolved repo_id.
        metadata_store.mark_synced(
            job_id,
            commit_hash=clone_res.commit_hash,
            cloned_at=getattr(clone_res, "cloned_at", "") or "",
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


@celery_app.task(bind=True, max_retries=3, acks_late=True, queue="ingestion")
def run_ingestion(
    self,
    repo_url: str,
    ref: str | None,
    force_reindex: bool,
    job_id: str,
    reuse_clone_path: str | None = None,
    reuse_repo_id: str | None = None,
    reuse_commit_hash: str | None = None,
    reuse_default_branch: str | None = None,
):
    logger.info("celery_ingestion_started", repo_url=repo_url, job_id=job_id)
    clone_res = None
    if reuse_clone_path:
        from app.ingestion.clone import CloneResult

        clone_path = Path(reuse_clone_path)
        if clone_path.is_dir():
            clone_res = CloneResult(
                repo_id=reuse_repo_id or job_id,
                clone_path=clone_path,
                default_branch=reuse_default_branch or "main",
                commit_hash=reuse_commit_hash or "",
                size_bytes=0,
            )
    try:
        run_ingestion_sync(
            repo_url,
            ref,
            force_reindex,
            job_id,
            clone_res=clone_res,
            re_raise=True,
        )
    except Exception as exc:
        logger.error("celery_ingestion_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=60) from exc
