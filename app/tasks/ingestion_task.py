# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""Celery task wrapper for ingestion — optional when Celery is installed."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.ingestion.pipeline import run_ingestion_sync
from app.observability.logging_config import logger

try:
    from app.tasks.celery_app import celery_app
except ImportError:  # pragma: no cover - dev without Celery
    celery_app = None  # type: ignore[assignment,misc]


if celery_app is not None:

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

else:

    def run_ingestion(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("Celery is not installed")
