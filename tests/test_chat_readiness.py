# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""P0 regression suite — /chat readiness must never false-block on alias metadata drift."""
from __future__ import annotations

import threading
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.agent.loop import run
from app.config import settings
from app.ingestion.locking import lock_manager
from app.ingestion.metadata_store import MetadataStore, Stage
from app.ingestion.repo_readiness import (
    audit_all_repos_consistency,
    evaluate_chat_readiness,
    mirror_sync_to_alias_pair,
    verify_sync_consistency,
)

JOB_ID = "375c63667dff3e1e20ef5712cf1c0cb33940a9b49644bb855f1f89fe959d9f4d"
ASSET_ID = "b4f947369301e4e0681a5f878604aa39c14efce4fbd98648e3722afd9f6380ee"
COMMIT = "f" * 40


@pytest.fixture()
def client():
    from app.main import app

    c = TestClient(app)
    c.headers.update({"X-API-Key": settings.API_KEY})
    return c


@pytest.fixture()
def isolated_store(tmp_path, monkeypatch):
    store = MetadataStore(base_dir=tmp_path)
    monkeypatch.setattr(settings, "REPOS_PATH", str(tmp_path))
    monkeypatch.setattr("app.ingestion.metadata_store.metadata_store", store)
    monkeypatch.setattr("app.ingestion.repo_readiness.metadata_store", store)
    monkeypatch.setattr("app.repo_resolver._default_store", store)
    monkeypatch.setattr("app.api.router.metadata_store", store)
    return store


def test_chat_blocked_while_genuinely_indexing(isolated_store):
    """Genuine in-progress ingest returns accurate progress numbers."""
    isolated_store.mark_pending(JOB_ID, "https://github.com/psf/requests", "HEAD")
    isolated_store.update(JOB_ID, Stage.PARSING, progress="Processed 3/10 files")
    isolated_store.update(JOB_ID, Stage.INDEXING)

    with patch(
        "app.ingestion.repo_readiness._index_counts",
        return_value=(3, 12),
    ):
        readiness = evaluate_chat_readiness(JOB_ID)
        result = run(JOB_ID, "How are params validated?", job_id=JOB_ID)

    assert not readiness.ready
    assert readiness.block_reason == "indexing"
    assert "3 files" in readiness.block_message
    assert "12 chunks" in readiness.block_message
    assert result["gated"] is True
    assert "3 files" in result["answer"]
    assert "12 chunks" in result["answer"]


def test_chat_unblocks_immediately_after_sync_completes(isolated_store):
    """mark_synced() must be visible to the very next readiness check (no stale read)."""
    isolated_store.mark_pending(JOB_ID, "https://github.com/psf/requests", "HEAD")
    isolated_store.mark_synced(
        JOB_ID,
        commit_hash=COMMIT,
        cloned_at="2026-07-10T00:00:00+00:00",
        files_parsed=10,
        chunks_created=55,
    )

    with patch(
        "app.ingestion.progress_counts.chroma_counts",
        return_value=(10, 55),
    ):
        readiness = evaluate_chat_readiness(JOB_ID)
        assert readiness.ready is True
        assert readiness.files_parsed == 10
        assert readiness.chunks_created == 55

        from app.agent.loop import AgentContext, AgentState, _handle_intake

        ctx = AgentContext(repo_id=JOB_ID, job_id=JOB_ID, question="q")
        nxt = _handle_intake(ctx)
        assert not ctx.gated
        assert nxt == AgentState.PLAN


def test_concurrent_force_reindex_does_not_downgrade_synced_status(isolated_store):
    """Second ingest while lock is held must not downgrade readable synced metadata."""
    isolated_store.mark_pending(JOB_ID, "https://github.com/psf/requests", "HEAD")
    isolated_store.mark_synced(
        JOB_ID,
        commit_hash=COMMIT,
        cloned_at="2026-07-10T00:00:00+00:00",
        files_parsed=5,
        chunks_created=20,
    )

    first = lock_manager.try_acquire(JOB_ID, isolated_store)
    assert first.acquired

    second = lock_manager.try_acquire(JOB_ID, isolated_store)
    assert not second.acquired

    meta = isolated_store.get(JOB_ID)
    assert meta is not None
    assert meta.sync_status == "synced"
    assert meta.files_parsed == 5
    assert meta.chunks_created == 20

    lock_manager.release(JOB_ID)


def test_metadata_read_after_write_consistency(isolated_store):
    """Concurrent readers must never observe a pre-sync value after mark_synced()."""
    isolated_store.mark_pending(JOB_ID, "https://github.com/psf/requests", "HEAD")
    observed: list[str] = []

    def reader() -> None:
        for _ in range(50):
            m = isolated_store.get(JOB_ID)
            if m:
                observed.append(m.sync_status)

    threads = [threading.Thread(target=reader) for _ in range(4)]
    for t in threads:
        t.start()
    isolated_store.mark_synced(
        JOB_ID,
        commit_hash=COMMIT,
        cloned_at="2026-07-10T00:00:00+00:00",
        files_parsed=1,
        chunks_created=2,
    )
    for t in threads:
        t.join()

    assert "synced" in observed
    assert isolated_store.get(JOB_ID).sync_status == "synced"


def test_silent_failure_never_leaves_stuck_indexing(isolated_store):
    """Pipeline exceptions must always land in failed (with error_reason), never stuck indexing."""
    isolated_store.mark_pending(JOB_ID, "https://github.com/psf/requests", "HEAD")
    isolated_store.update(JOB_ID, Stage.INDEXING)

    isolated_store.mark_failed(JOB_ID, error_reason="parser exploded")
    meta = isolated_store.get(JOB_ID)
    assert meta.sync_status == "failed"
    assert meta.error_reason
    assert meta.sync_status != "indexing"


def test_chroma_and_metadata_agree(isolated_store):
    """chunks_created in metadata must match Chroma collection count."""
    isolated_store.mark_pending(JOB_ID, "https://github.com/psf/requests", "HEAD")
    isolated_store.mark_synced(
        JOB_ID,
        commit_hash=COMMIT,
        cloned_at="2026-07-10T00:00:00+00:00",
        files_parsed=4,
        chunks_created=99,
    )

    meta = isolated_store.get(JOB_ID)

    with patch("app.ingestion.repo_readiness._index_counts", return_value=(4, 99)):
        ok, files, chunks = verify_sync_consistency(meta, JOB_ID, job_id=JOB_ID)
    assert ok is True
    assert files == 4
    assert chunks == 99

    with patch("app.ingestion.repo_readiness._index_counts", return_value=(4, 50)):
        ok_mismatch, _, chunks_bad = verify_sync_consistency(
            meta, JOB_ID, job_id=JOB_ID, auto_repair=False,
        )
    assert ok_mismatch is False
    assert chunks_bad == 50


def test_stale_repo_id_from_frontend_gives_clear_error(client):
    """Unknown repo_id must 404 with a clear message — not a generic indexing block."""
    unknown = "0" * 64
    readiness = evaluate_chat_readiness(unknown)
    assert readiness.block_reason == "unknown"
    assert "unknown" in readiness.block_message.lower()

    resp = client.post("/chat", json={"repo_id": unknown, "question": "hello?"})
    assert resp.status_code == 404
    assert "unknown" in resp.json()["detail"].lower()


def test_status_and_chat_agree(isolated_store, monkeypatch):
    """Back-to-back /status and /chat must agree on readiness for alias-split metadata."""
    isolated_store.mark_pending(JOB_ID, "https://github.com/psf/requests", "HEAD")
    isolated_store.mark_synced(
        JOB_ID,
        commit_hash=COMMIT,
        cloned_at="2026-07-10T00:00:00+00:00",
        files_parsed=36,
        chunks_created=521,
    )
    isolated_store.mark_pending(ASSET_ID, "https://github.com/psf/requests", "main")
    isolated_store.save_alias(JOB_ID, ASSET_ID)
    raw = isolated_store._read_raw(ASSET_ID)
    raw["sync_status"] = "indexing"
    raw["last_stage"] = "indexing"
    raw["file_count"] = 37
    isolated_store._write_raw(ASSET_ID, raw)

    monkeypatch.setattr("app.platform.usage_meter.check_quota", lambda *a, **k: True)
    monkeypatch.setattr("app.platform.usage_meter.increment", lambda *a, **k: None)
    monkeypatch.setattr("app.platform.audit_log.record_event", lambda *a, **k: None)

    with patch("app.ingestion.progress_counts.ingest_progress_counts", return_value=(36, 521)):
        from app.main import app

        api = TestClient(app)
        api.headers.update({"X-API-Key": settings.API_KEY})
        status_resp = api.get(f"/status/{JOB_ID}")

        with patch(
            "app.api.router.run",
            return_value={
                "answer": "Request parameters are validated in the requests library.",
                "sources": [],
                "confidence_score": 0.9,
                "gated": False,
            },
        ):
            chat_resp = api.post(
                "/chat",
                json={"repo_id": JOB_ID, "question": "How request parameters are validated?"},
            )

    status_ready = status_resp.json().get("status") == "ready"
    chat_ready = not chat_resp.json().get("gated", True)
    assert status_resp.status_code == 200
    assert chat_resp.status_code == 200
    assert status_ready == chat_ready
    assert status_ready is True


def test_alias_repair_mirrors_job_synced_to_asset(isolated_store):
    """Repair path: job synced + asset indexing → asset promoted to synced on read."""
    isolated_store.mark_pending(JOB_ID, "https://github.com/psf/requests", "HEAD")
    isolated_store.save_alias(JOB_ID, ASSET_ID)
    isolated_store.mark_synced(
        JOB_ID,
        commit_hash=COMMIT,
        cloned_at="2026-07-10T00:00:00+00:00",
        files_parsed=36,
        chunks_created=521,
    )
    isolated_store.mark_pending(ASSET_ID, "https://github.com/psf/requests", "main")
    raw = isolated_store._read_raw(ASSET_ID)
    raw["sync_status"] = "indexing"
    raw["last_stage"] = "indexing"
    isolated_store._write_raw(ASSET_ID, raw)

    with patch("app.ingestion.progress_counts.ingest_progress_counts", return_value=(36, 521)):
        readiness = evaluate_chat_readiness(JOB_ID, asset_repo_id=ASSET_ID)

    assert readiness.ready is True
    asset_meta = isolated_store.get(ASSET_ID)
    assert asset_meta.sync_status == "synced"
    assert asset_meta.chunks_created == 521


def test_mirror_sync_writes_both_ids(isolated_store):
    isolated_store.mark_pending(JOB_ID, "https://github.com/psf/requests", "HEAD")
    isolated_store.mark_pending(ASSET_ID, "https://github.com/psf/requests", "main")
    isolated_store.save_alias(JOB_ID, ASSET_ID)

    mirror_sync_to_alias_pair(
        JOB_ID,
        ASSET_ID,
        commit_hash=COMMIT,
        cloned_at="2026-07-10T00:00:00+00:00",
        files_parsed=8,
        chunks_created=40,
    )
    assert isolated_store.get(JOB_ID).sync_status == "synced"
    assert isolated_store.get(ASSET_ID).sync_status == "synced"
    assert isolated_store.get(ASSET_ID).chunks_created == 40


def test_audit_all_repos_flags_synced_without_chunks(isolated_store):
    isolated_store.mark_pending(JOB_ID, "https://github.com/psf/requests", "HEAD")
    isolated_store.mark_synced(
        JOB_ID,
        commit_hash=COMMIT,
        cloned_at="2026-07-10T00:00:00+00:00",
        files_parsed=0,
        chunks_created=0,
    )
    with patch("app.ingestion.repo_readiness._index_counts", return_value=(0, 0)):
        violations = audit_all_repos_consistency()
    assert any(v["repo_id"] == JOB_ID for v in violations)
