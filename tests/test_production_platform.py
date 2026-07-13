# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""Production hardening: path jail, API keys, platform endpoints."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.platform.api_keys import create_api_key, resolve_api_key
from app.security.path_jail import PathJailError, resolve_jailed_path


def test_path_jail_blocks_traversal(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "safe.py").write_text("ok")
    assert resolve_jailed_path(root, "safe.py").name == "safe.py"
    with pytest.raises(PathJailError):
        resolve_jailed_path(root, "../../../etc/passwd")


def test_path_jail_strips_clone_prefix(tmp_path: Path):
    root = tmp_path / "clone"
    root.mkdir()
    (root / "main.py").write_text("x")
    resolved = resolve_jailed_path(root, "repos/abc/clone/main.py")
    assert resolved.name == "main.py"


def test_resolve_api_key_legacy(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "API_KEY", "super-secret-key-for-tests-only")
    ctx = resolve_api_key("super-secret-key-for-tests-only")
    assert ctx is not None
    assert ctx.org_id == "default"


def test_weak_key_rejected_in_production(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "API_KEY", "dev-secret-key")
    from app.platform.api_keys import is_production_api_key_valid

    assert is_production_api_key_valid() is False


def test_platform_delete_requires_auth():
    client = TestClient(app)
    resp = client.delete("/platform/repos/fake-id")
    assert resp.status_code in (401, 403, 422)


def test_platform_export_and_audit(mock_api_key, tmp_path, monkeypatch):
    from app.config import settings
    from app.ingestion.metadata_store import metadata_store

    repos_path = tmp_path / "repos"
    repos_path.mkdir()
    monkeypatch.setattr(settings, "REPOS_PATH", str(repos_path))
    audit_path = tmp_path / "audit_log.jsonl"
    monkeypatch.setattr("app.platform.audit_log._AUDIT_PATH", audit_path)

    repo_id = "test-repo-job"
    metadata_store.mark_pending(repo_id, "https://github.com/foo/bar", "main")
    metadata_store.mark_synced(repo_id, commit_hash="abc123", cloned_at="2026-01-01T00:00:00Z")

    client = TestClient(app)
    export = client.get(
        f"/platform/repos/{repo_id}/export",
        headers={"X-API-Key": "dev-secret-key"},
    )
    assert export.status_code == 200
    assert export.json()["metadata"]["repo_id"] == repo_id

    audit = client.get("/platform/audit", headers={"X-API-Key": "dev-secret-key"})
    assert audit.status_code == 200
    assert isinstance(audit.json(), list)


def test_create_api_key_roundtrip(tmp_path, monkeypatch):
    from app.config import settings

    keys_file = tmp_path / "api_keys.json"
    monkeypatch.setattr("app.platform.api_keys._KEYS_PATH", keys_file)
    monkeypatch.setattr(settings, "API_KEY", "primary-key-for-admin-tests-only")

    secret = create_api_key("acme", "ci")
    ctx = resolve_api_key(secret)
    assert ctx is not None
    assert ctx.org_id == "acme"
    assert ctx.label == "ci"


def test_org_isolation_blocks_cross_tenant_export(mock_api_key, tmp_path, monkeypatch):
    from app.config import settings
    from app.ingestion.metadata_store import metadata_store

    repos_path = tmp_path / "repos"
    repos_path.mkdir()
    monkeypatch.setattr(settings, "REPOS_PATH", str(repos_path))

    repo_id = "other-org-repo"
    metadata_store.mark_pending(repo_id, "https://github.com/foo/bar", "main")
    metadata_store.mark_synced(repo_id, commit_hash="abc123", cloned_at="2026-01-01T00:00:00Z")
    raw = metadata_store._read_raw(repo_id)
    assert raw is not None
    raw["org_id"] = "acme"
    metadata_store._write_raw(repo_id, raw)

    client = TestClient(app)
    resp = client.get(
        f"/platform/repos/{repo_id}/export",
        headers={"X-API-Key": "dev-secret-key"},
    )
    assert resp.status_code == 403
