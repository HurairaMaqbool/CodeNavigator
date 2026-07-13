# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Regression — job_id partial BM25 index must not shadow full asset alias index."""
from __future__ import annotations

from unittest.mock import patch

from app.agent.confidence import (
    _load_repo_metadata,
    check_file_existence,
)


def test_load_repo_metadata_prefers_larger_index():
    job_records = [{"metadata": {"file_path": "a.py", "chunk": "x"}}] * 5
    asset_records = [{"metadata": {"file_path": f"src/f{i}.py", "chunk": "y"}} for i in range(50)]

    def _fake_read(rid: str):
        if rid == "job-id":
            return job_records
        if rid == "asset-id":
            return asset_records
        return []

    with patch("app.agent.confidence._bm25_lookup_ids", return_value=["asset-id", "job-id"]), patch(
        "app.agent.confidence._read_bm25_records", side_effect=_fake_read
    ):
        loaded = _load_repo_metadata("job-id")

    assert len(loaded) == 50


def test_check_file_existence_uses_merged_index_paths():
    cite = {
        "file_path": "src/requests/sessions.py",
        "repo_id": "job-id",
        "unparseable": False,
    }
    fake_meta = type("M", (), {"sync_status": "synced"})()

    with patch("app.agent.confidence._bm25_lookup_ids", return_value=["asset-id", "job-id"]), patch(
        "app.agent.confidence.metadata_store.get", return_value=fake_meta
    ), patch(
        "app.agent.confidence._indexed_paths_for_repo",
        return_value={"src/requests/sessions.py"},
    ), patch("app.agent.confidence._clone_file_path", return_value=None):
        assert check_file_existence(cite) is True
