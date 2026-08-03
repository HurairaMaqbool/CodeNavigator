# Copyright (c) 2026 Huraira Maqbool
# Test auto-recovery during normal re-ingestion requests (force_reindex=False).

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.ingestion.metadata_store import metadata_store, Stage
from app.retrieval.vector_store import get_collection, store_chunks, delete_repo
from app.parsing.chunker import CodeChunk
from app.ingestion.pipeline import run_ingestion_sync

def test_normal_reingest_auto_promotes_force_reindex_on_failed_status(tmp_path):
    repo_id = "test_normal_reingest_repo_auto"
    
    # 1. Store 5 stale chunks in vector store
    delete_repo(repo_id)
    stale_chunk = CodeChunk(
        chunk_text="def stale_func(): pass",
        file_path="src/stale.py",
        display_path="src/stale.py",
        normalized_path="src/stale.py",
        function_name="stale_func",
        start_line=1,
        end_line=5,
        type="function",
        language="python",
        fingerprint="fp_stale",
        class_name=None,
    )
    store_chunks(repo_id, [stale_chunk], force_reindex=True)
    
    # Mark repo as FAILED in metadata store
    metadata_store.mark_pending(repo_id, "https://github.com/psf/requests.git", "HEAD")
    metadata_store.mark_failed(repo_id, error_reason="Crashed during prior run")
    
    meta = metadata_store.get(repo_id)
    assert meta is not None and meta.sync_status == Stage.FAILED.value
    
    # 2. Trigger normal re-ingestion with force_reindex=False
    # Mock clone_repo and parse_file to supply 1 new chunk
    mock_clone = MagicMock()
    mock_clone.repo_id = repo_id
    mock_clone.commit_hash = "abc123456789"
    mock_clone.cloned_at = "2026-07-23T12:00:00Z"
    mock_clone.clone_path = tmp_path / "clone"
    (tmp_path / "clone").mkdir(parents=True, exist_ok=True)
    (tmp_path / "clone" / "main.py").write_text("def new_func(): pass", encoding="utf-8")
    
    from app.ingestion.file_filter import FileRecord
    f_item = FileRecord(
        path=str(tmp_path / "clone" / "main.py"),
        display_path="main.py",
        normalized_path="main.py",
        language="python",
        size_bytes=20,
    )
    
    with patch("app.ingestion.pipeline.clone_repo", return_value=mock_clone):
        with patch("app.ingestion.pipeline.filter_repo_files", return_value=[f_item]):
            # Send normal re-ingestion (force_reindex=False)
            res = run_ingestion_sync("https://github.com/psf/requests.git", "HEAD", force_reindex=False, job_id=repo_id)
            assert res is True
            
            # Confirm metadata is now SYNCED
            updated_meta = metadata_store.get(repo_id)
            assert updated_meta.sync_status == Stage.SYNCED.value
            
            # Confirm vector store was wiped of stale chunk and only contains 1 new chunk
            col = get_collection(repo_id)
            assert col.count() == 1
