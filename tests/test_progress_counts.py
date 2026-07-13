# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Tests for progress_counts Chroma vs metadata alignment."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.ingestion.progress_counts import ingest_progress_counts


def test_prefers_chroma_over_stale_metadata():
    meta = MagicMock(
        files_parsed=36,
        chunks_created=521,
    )
    with patch(
        "app.ingestion.progress_counts.chroma_counts",
        return_value=(30, 15),
    ):
        files, chunks = ingest_progress_counts(meta, "asset123", job_id="job456")
    assert files == 30
    assert chunks == 15


def test_falls_back_to_metadata_when_chroma_empty():
    meta = MagicMock(
        files_parsed=36,
        chunks_created=521,
    )
    with patch(
        "app.ingestion.progress_counts.chroma_counts",
        return_value=(0, 0),
    ):
        files, chunks = ingest_progress_counts(meta, "asset123", job_id="job456")
    assert files == 36
    assert chunks == 521
