# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Unit tests for the Celery ingestion task wrapper.

Celery registers the decorated function as a task object (PromiseProxy).
``run_ingestion.__wrapped__`` is the bound method on the real task instance
(with ``bind=True``, Celery pre-binds ``self`` to the task object).  We test
through ``__wrapped__`` to bypass the Celery worker dispatch machinery while
still exercising the real business logic.

For tests that need to intercept ``self.retry``, we patch the attribute
directly on the live task object.
"""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.tasks.ingestion_task import run_ingestion
from app.ingestion.clone import CloneResult


def test_run_ingestion_celery_task_success():
    """Verify run_ingestion calls run_ingestion_sync with correct arguments."""
    with patch("app.tasks.ingestion_task.run_ingestion_sync") as mock_sync:
        run_ingestion.__wrapped__(
            repo_url="https://github.com/foo/bar",
            ref="main",
            force_reindex=False,
            job_id="job123",
        )
        mock_sync.assert_called_once_with(
            "https://github.com/foo/bar",
            "main",
            False,
            "job123",
            clone_res=None,
            re_raise=True,
        )


def test_run_ingestion_celery_task_with_reuse_paths():
    """Verify reuse clone path parameters build CloneResult correctly."""
    with patch("app.tasks.ingestion_task.run_ingestion_sync") as mock_sync, \
         patch("pathlib.Path.is_dir", return_value=True):

        run_ingestion.__wrapped__(
            repo_url="https://github.com/foo/bar",
            ref="main",
            force_reindex=False,
            job_id="job123",
            reuse_clone_path="/fake/clone/path",
            reuse_repo_id="asset456",
            reuse_commit_hash="abc123hash",
            reuse_default_branch="dev",
        )

        mock_sync.assert_called_once()
        _args, kwargs = mock_sync.call_args
        clone_res = kwargs["clone_res"]
        assert isinstance(clone_res, CloneResult)
        assert clone_res.repo_id == "asset456"
        assert clone_res.clone_path == Path("/fake/clone/path")
        assert clone_res.commit_hash == "abc123hash"
        assert clone_res.default_branch == "dev"


def test_run_ingestion_celery_task_failure_triggers_retry():
    """Verify transient ingestion failures trigger Celery self.retry logic."""
    retry_exc = Exception("retried_task")

    with patch("app.tasks.ingestion_task.run_ingestion_sync", side_effect=ValueError("connection_lost")), \
         patch.object(run_ingestion, "retry", side_effect=retry_exc) as mock_retry:

        with pytest.raises(Exception, match="retried_task"):
            run_ingestion.__wrapped__(
                repo_url="https://github.com/foo/bar",
                ref="main",
                force_reindex=False,
                job_id="job123",
            )

        mock_retry.assert_called_once()
        _args, kwargs = mock_retry.call_args
        assert "exc" in kwargs
        assert isinstance(kwargs["exc"], ValueError)
        assert kwargs["countdown"] == 60
