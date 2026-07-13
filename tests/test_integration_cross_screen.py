# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Cross-screen integration contract tests (backend shared truth)."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings

JOB_ID = "375c63667dff3e1e20ef5712cf1c0cb33940a9b49644bb855f1f89fe959d9f4d"
COMMIT = "a" * 40


@pytest.fixture()
def client():
    from app.main import app

    c = TestClient(app)
    c.headers.update({"X-API-Key": settings.API_KEY})
    return c


@pytest.fixture()
def isolated_store(tmp_path, monkeypatch):
    from app.ingestion.metadata_store import MetadataStore

    store = MetadataStore(base_dir=tmp_path)
    monkeypatch.setattr(settings, "REPOS_PATH", str(tmp_path))
    monkeypatch.setattr("app.ingestion.metadata_store.metadata_store", store)
    monkeypatch.setattr("app.ingestion.repo_readiness.metadata_store", store)
    monkeypatch.setattr("app.repo_resolver._default_store", store)
    monkeypatch.setattr("app.api.router.metadata_store", store)
    return store


def _seed_synced_repo(store, *, files=10, chunks=588):
    store.mark_pending(JOB_ID, "https://github.com/psf/requests", "main")
    store.mark_synced(
        JOB_ID,
        commit_hash=COMMIT,
        cloned_at="2026-07-12T00:00:00+00:00",
        files_parsed=files,
        chunks_created=chunks,
    )


def test_status_and_eval_health_chunk_alignment(client, isolated_store):
    """Scenario E — /status and /eval/health agree on chunk counts for same repo."""
    _seed_synced_repo(isolated_store, chunks=588)

    with patch(
        "app.ingestion.repo_readiness._index_counts",
        return_value=(10, 588),
    ), patch(
        "app.ingestion.index_integrity.chroma_counts",
        return_value=(10, 588),
    ), patch(
        "app.retrieval.hybrid_search.search_hybrid",
        return_value=[{"path": "requests/models.py"}],
    ), patch(
        "app.retrieval.bm25_store._index_path_for",
        return_value=__import__("pathlib").Path("/tmp/bm25.idx"),
    ), patch(
        "pathlib.Path.exists",
        return_value=True,
    ):
        status = client.get(f"/status/{JOB_ID}")
        assert status.status_code == 200
        health = client.get(f"/eval/health/{JOB_ID}")
        assert health.status_code == 200

        s_body = status.json()
        h_body = health.json()
        details = h_body.get("details") or {}

        assert s_body["chunks_created"] == 588
        assert details.get("chunks_created") == 588
        assert details.get("chroma_chunk_count") == 588


def test_invalid_compare_does_not_break_status(client, isolated_store):
    """Scenario D — eval compare errors are isolated from ingest status."""
    _seed_synced_repo(isolated_store, chunks=100)

    with patch(
        "app.ingestion.repo_readiness._index_counts",
        return_value=(5, 100),
    ):
        before = client.get(f"/status/{JOB_ID}")
        assert before.status_code == 200

        bad = client.get("/eval/compare?baseline=nope&candidate=nope")
        assert bad.status_code in (404, 422, 400)

        after = client.get(f"/status/{JOB_ID}")
        assert after.status_code == 200
        assert after.json()["chunks_created"] == before.json()["chunks_created"]


def test_status_scoped_to_active_job(client, isolated_store):
    """Scenario B — status endpoint returns data for requested job_id only."""
    _seed_synced_repo(isolated_store, chunks=521)

    with patch(
        "app.ingestion.repo_readiness._index_counts",
        return_value=(8, 521),
    ):
        resp = client.get(f"/status/{JOB_ID}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["job_id"] == JOB_ID
        assert body["chunks_created"] == 521


def test_repo_sync_invalidation_module_exports():
    """Frontend repo-sync module exists and exports invalidation helpers."""
    from pathlib import Path

    sync_ts = Path("frontend-next/lib/repo-sync.ts")
    assert sync_ts.exists()
    text = sync_ts.read_text(encoding="utf-8")
    assert "invalidateRepoQueries" in text
    assert "invalidateAfterRepoMutation" in text
    assert "platformRepos" in text
    assert "evalHistory" in text
    assert "goldenStatus" in text


def test_app_context_clears_repo_on_clear_session():
    """Scenario B — clearSession wipes repo + chat scope (frontend contract)."""
    from pathlib import Path

    ctx = Path("frontend-next/lib/context/app-context.tsx").read_text(encoding="utf-8")
    assert "clearSession" in ctx
    assert "setRepoId(null)" in ctx
    assert "setChatByRepo({})" in ctx
    assert "newSessionId()" in ctx


def test_repo_sync_bridge_invalidates_on_repo_change():
    from pathlib import Path

    bridge = Path("frontend-next/components/shared/repo-sync-bridge.tsx").read_text(
        encoding="utf-8",
    )
    assert "RepoSyncBridge" in bridge
    assert "invalidateRepoQueries" in bridge
    assert "prevRef" in bridge


def test_platform_repos_chunk_fields(client, isolated_store):
    """Scenario E — /platform/repos exposes chroma + integrity flags."""
    _seed_synced_repo(isolated_store, chunks=588)
    raw = isolated_store._read_raw(JOB_ID)
    assert raw is not None
    raw["org_id"] = "default"
    isolated_store._write_raw(JOB_ID, raw)

    with patch(
        "app.ingestion.index_integrity.chroma_chunk_count",
        return_value=588,
    ):
        resp = client.get("/platform/repos")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["chunks_created"] == 588
    assert rows[0]["chroma_chunks"] == 588
    assert rows[0]["index_integrity_ok"] is True
