# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Regression tests — /status must reflect pipeline progress and never stall polling."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.ingestion.metadata_store import MetadataStore, Stage, metadata_store
from app.main import app

JOB_ID = "375c63667dff3e1e20ef5712cf1c0cb33940a9b49644bb855f1f89fe959d9f4d"


@pytest.fixture()
def client():
    c = TestClient(app)
    c.headers.update({"X-API-Key": settings.API_KEY})
    return c


def test_status_maps_indexing_stage_to_processing(tmp_path, monkeypatch):
    """Intermediate sync_status values must not leave API status unset (poll hang)."""
    store = MetadataStore(base_dir=tmp_path)
    monkeypatch.setattr("app.ingestion.metadata_store.metadata_store", store)
    monkeypatch.setattr("app.api.router.metadata_store", store)
    monkeypatch.setattr("app.ingestion.repo_readiness.metadata_store", store)
    monkeypatch.setattr("app.repo_resolver._default_store", store)

    store.mark_pending(JOB_ID, "https://github.com/psf/requests", "HEAD")
    store.update(JOB_ID, Stage.INDEXING, progress="Indexed chunks in vector store")

    with patch("app.api.router._resolve_repo_meta") as mock_resolve, patch(
        "app.ingestion.repo_readiness._index_counts",
        return_value=(0, 0),
    ):
        meta = store.get(JOB_ID)
        mock_resolve.return_value = (meta, JOB_ID)

        resp = TestClient(app).get(
            f"/status/{JOB_ID}",
            headers={"X-API-Key": settings.API_KEY},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["sync_status"] == "indexing"
    assert body["status"] == "processing"


def test_status_returns_files_and_chunks_when_synced(tmp_path, monkeypatch):
    store = MetadataStore(base_dir=tmp_path)
    monkeypatch.setattr("app.ingestion.metadata_store.metadata_store", store)
    monkeypatch.setattr("app.api.router.metadata_store", store)
    monkeypatch.setattr("app.ingestion.repo_readiness.metadata_store", store)
    monkeypatch.setattr("app.repo_resolver._default_store", store)

    store.mark_pending(JOB_ID, "https://github.com/psf/requests", "HEAD")
    store.mark_synced(
        JOB_ID,
        commit_hash="f" * 40,
        cloned_at="2026-07-10T00:00:00+00:00",
        files_parsed=42,
        chunks_created=318,
    )

    with patch("app.api.router._resolve_repo_meta") as mock_resolve:
        meta = store.get(JOB_ID)
        mock_resolve.return_value = (meta, JOB_ID)

        resp = TestClient(app).get(
            f"/status/{JOB_ID}",
            headers={"X-API-Key": settings.API_KEY},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["sync_status"] == "synced"
    assert body["files_parsed"] == 42
    assert body["chunks_created"] == 318


def test_celery_skipped_when_redis_up_but_no_workers(monkeypatch):
    """Jobs must not sit in Celery queue when no worker is running."""
    bg_tasks = MagicMock()
    monkeypatch.setattr("app.redis_client.ping_redis", lambda: True)
    monkeypatch.setattr("app.api.router._celery_workers_available", lambda: False)
    monkeypatch.setattr(
        "app.api.router.lock_manager.try_acquire",
        lambda *a, **k: MagicMock(acquired=True),
    )
    monkeypatch.setattr("app.api.router.lock_manager.release", lambda *a, **k: None)
    monkeypatch.setattr("app.api.router.metadata_store.mark_pending", lambda *a, **k: None)
    monkeypatch.setattr("app.platform.usage_meter.check_quota", lambda *a, **k: True)
    monkeypatch.setattr("app.platform.usage_meter.increment", lambda *a, **k: None)
    monkeypatch.setattr("app.platform.audit_log.record_event", lambda *a, **k: None)

    delay_mock = MagicMock()
    monkeypatch.setattr("app.tasks.ingestion_task.run_ingestion.delay", delay_mock)
    sync_mock = MagicMock()
    monkeypatch.setattr("app.tasks.ingestion_task.run_ingestion_sync", sync_mock)

    from app.api.router import trigger_ingest

    trigger_ingest("https://github.com/psf/requests", None, False, bg_tasks)

    delay_mock.assert_not_called()
    bg_tasks.add_task.assert_called_once()


def test_live_repo_status_reports_counts_when_index_exists(client):
    """End-to-end: known requests repo_id should report non-zero chunks when synced."""
    resp = client.get(f"/status/{JOB_ID}")
    if resp.status_code == 404:
        pytest.skip("repo metadata not present in this environment")

    body = resp.json()
    if body.get("sync_status") != "synced":
        pytest.skip(f"repo not synced in this environment ({body.get('sync_status')})")

    assert body["status"] == "ready"
    assert body["chunks_created"] > 0, "synced repo must expose chunk count in /status"
    assert body["files_parsed"] > 0, "synced repo must expose file count in /status"
