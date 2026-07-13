# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Regression tests for index_integrity — prevents metadata/chroma drift class."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.ingestion.index_integrity import (
    assert_post_ingest_integrity,
    check_index_integrity,
)


def test_chroma_chunk_count_fast_path():
    with patch("app.retrieval.vector_store.get_collection") as gc:
        col = gc.return_value
        col.count.return_value = 588
        from app.ingestion.index_integrity import chroma_chunk_count

        assert chroma_chunk_count("asset-a", "job-b") == 588
        col.count.assert_called()


def test_check_index_integrity_fails_on_stale_metadata():
    with patch("app.ingestion.index_integrity.chroma_counts", return_value=(2, 15)):
        report = check_index_integrity(
            "asset123",
            job_id="job456",
            metadata_chunks=521,
            min_chunks=50,
        )
    assert report.ok is False
    assert report.mismatch is True
    assert report.chroma_chunks == 15
    assert any("521" in e or "15" in e for e in report.errors)


def test_check_index_integrity_passes_when_aligned():
    with patch("app.ingestion.index_integrity.chroma_counts", return_value=(36, 521)):
        report = check_index_integrity(
            "asset123",
            job_id="job456",
            metadata_chunks=521,
            min_chunks=50,
        )
    assert report.ok is True
    assert report.mismatch is False


def test_post_ingest_raises_on_mismatch():
    with patch("app.ingestion.index_integrity.chroma_counts", return_value=(1, 1)):
        with pytest.raises(RuntimeError, match="integrity"):
            assert_post_ingest_integrity(
                "asset123",
                job_id="job456",
                expected_chunks=521,
            )


def test_post_ingest_passes_when_counts_match():
    with patch("app.ingestion.index_integrity.chroma_counts", return_value=(36, 521)):
        with patch("app.ingestion.index_integrity.check_bm25_integrity", return_value=[]):
            report = assert_post_ingest_integrity(
                "asset123",
                job_id="job456",
                expected_chunks=521,
            )
    assert report.ok is True


def test_post_ingest_fails_when_bm25_missing():
    with patch("app.ingestion.index_integrity.chroma_counts", return_value=(36, 521)):
        with patch("app.ingestion.index_integrity.bm25_chunk_count", return_value=0):
            with patch(
                "app.ingestion.index_integrity.check_bm25_integrity",
                return_value=["BM25 index missing"],
            ):
                with pytest.raises(RuntimeError, match="BM25"):
                    assert_post_ingest_integrity(
                        "asset123",
                        job_id="job456",
                        expected_chunks=521,
                    )
