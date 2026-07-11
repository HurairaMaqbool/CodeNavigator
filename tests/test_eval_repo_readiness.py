# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Regression: eval readiness must match /status for the same repo_id."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.ingestion.repo_readiness import is_repo_ready
from eval.health_check import run_full_eval_precheck
from eval.run_eval import _filter_golden_for_repo, _resolve_golden_path, load_golden_set

JOB = "375c63667dff3e1e20ef5712cf1c0cb33940a9b49644bb855f1f89fe959d9f4d"
ASSET = "b4f947369301e4e0681a5f878604aa39c14efce4fbd98648e3722afd9f6380ee"


def test_resolve_golden_path_uses_eval_set_when_target_repo_set():
  path = _resolve_golden_path(target_repo_id=JOB)
  assert path.as_posix().endswith("tests/eval_set.json")


def test_data_golden_set_has_no_repo_id_on_entries():
    entries = load_golden_set(target_repo_id=None)
    assert entries
    assert not any(e.get("repo_id") for e in entries[:3])


def test_filter_golden_for_repo_uses_eval_set_entries():
    entries = load_golden_set(target_repo_id=JOB)
    assert entries
    assert all(e.get("repo_id") == JOB for e in entries)


def test_empty_repo_id_fails_readiness():
    ready = is_repo_ready("")
    assert ready.ready is False
    pre = run_full_eval_precheck("", include_agent_probe=False)
    assert pre.ok is False
    assert "missing" in pre.errors[0].lower() or "ingest" in pre.errors[0].lower()


@patch("eval.run_eval.is_repo_ready")
def test_run_golden_set_precheck_uses_target_repo_id(mock_ready):
    from eval.run_eval import run_golden_set

    mock_ready.return_value = MagicMock(
        ready=False,
        sync_status="missing",
        block_message="not ready",
        meta=None,
    )
    with pytest.raises(ValueError, match="not fully ingested"):
        run_golden_set(target_repo_id=JOB)
    mock_ready.assert_called_once_with(JOB)


def test_status_and_eval_health_agree_on_synced_job():
    from app.ingestion.repo_readiness import readiness_snapshot

    ready = is_repo_ready(JOB)
    snap = readiness_snapshot(JOB)
    pre = run_full_eval_precheck(JOB, include_agent_probe=False)
    assert ready.ready == pre.ok
    assert snap["ready"] == ready.ready
    assert snap["sync_status"] == "synced"
    assert snap["chunks_created"] >= 50


def test_readiness_snapshot_missing_repo():
    from app.ingestion.repo_readiness import readiness_snapshot

    snap = readiness_snapshot("")
    assert snap["ready"] is False
    assert snap["sync_status"] == "missing"
