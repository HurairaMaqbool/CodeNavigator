# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Tests for eval job polling and background timeout helpers."""
from __future__ import annotations

import concurrent.futures
from unittest.mock import MagicMock, patch

from eval.eval_store import _normalize_runs


def test_normalize_runs_unique_ids_for_same_version():
    raw = [
        {"version": "abc1234", "timestamp": "2026-01-01T00:00:00+00:00"},
        {"version": "abc1234", "timestamp": "2026-01-02T00:00:00+00:00"},
    ]
    out = _normalize_runs(raw)
    assert out[0]["run_id"] != out[1]["run_id"]


def test_run_job_with_timeout_marks_error():
    from app.api.router import _run_job_with_timeout

    job_id = "test-job-timeout"
    future = MagicMock()
    future.result.side_effect = concurrent.futures.TimeoutError()
    pool = MagicMock()
    pool.submit.return_value = future
    pool.__enter__.return_value = pool

    with patch("app.api.router._set_eval_job") as mock_set, patch(
        "concurrent.futures.ThreadPoolExecutor",
        return_value=pool,
    ), patch("app.config.settings") as mock_settings:
        mock_settings.EVAL_JOB_MAX_SECONDS = 120
        try:
            _run_job_with_timeout(job_id, "Test eval", lambda: {"ok": True})
        except TimeoutError:
            pass

    mock_set.assert_any_call(
        job_id,
        status="error",
        error="Test eval timed out after 120s",
    )
