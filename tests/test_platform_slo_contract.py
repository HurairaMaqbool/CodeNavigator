# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Platform module SLO contract tests — usage, billing, keys, audit."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def platform_client(tmp_path, monkeypatch):
    from app.config import settings

    keys_path = tmp_path / "api_keys.json"
    audit_path = tmp_path / "audit.jsonl"
    meter_path = tmp_path / "meter.json"
    subs_path = tmp_path / "subs.json"
    monkeypatch.setattr("app.platform.api_keys._KEYS_PATH", keys_path)
    monkeypatch.setattr("app.platform.audit_log._AUDIT_PATH", audit_path)
    monkeypatch.setattr("app.platform.usage_meter._METER_PATH", meter_path)
    monkeypatch.setattr("app.platform.billing.subscriptions._SUBS_PATH", subs_path)
    monkeypatch.setattr("app.platform.db.stores.use_postgres", lambda: False)
    monkeypatch.setattr(settings, "API_KEY", "dev-secret-key")
    return TestClient(app)


def test_usage_includes_eval_limit(platform_client):
    resp = platform_client.get(
        "/platform/usage",
        headers={"X-API-Key": "dev-secret-key"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "eval_per_month" in body["limits"]
    assert "metrics" in body
    assert body["org_id"] == "default"


def test_api_key_list_never_returns_full_secret(platform_client):
    create = platform_client.post(
        "/platform/api-keys",
        json={"label": "slo-test"},
        headers={"X-API-Key": "dev-secret-key"},
    )
    assert create.status_code == 200
    full = create.json()["api_key"]
    assert len(full) > 16

    listed = platform_client.get(
        "/platform/api-keys",
        headers={"X-API-Key": "dev-secret-key"},
    )
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) >= 1
    for row in rows:
        assert "api_key" not in row
        assert full not in json.dumps(row)
        assert row["key_prefix"].endswith("…")


def test_create_key_rejects_extra_org_id(platform_client):
    resp = platform_client.post(
        "/platform/api-keys",
        json={"org_id": "evil", "label": "x"},
        headers={"X-API-Key": "dev-secret-key"},
    )
    assert resp.status_code == 422


def test_audit_records_key_lifecycle(platform_client):
    create = platform_client.post(
        "/platform/api-keys",
        json={"label": "audit-me"},
        headers={"X-API-Key": "dev-secret-key"},
    )
    secret = create.json()["api_key"]
    prefix = secret[:8]
    platform_client.request(
        "DELETE",
        "/platform/api-keys",
        headers={"X-API-Key": "dev-secret-key"},
        json={"key_prefix": prefix},
    )
    audit = platform_client.get(
        "/platform/audit",
        headers={"X-API-Key": "dev-secret-key"},
    )
    actions = [e["action"] for e in audit.json()]
    assert "api_key.created" in actions
    assert "api_key.revoked" in actions


def test_platform_endpoints_require_auth():
    client = TestClient(app)
    for path in ("/platform/usage", "/platform/audit", "/platform/api-keys"):
        assert client.get(path).status_code == 401


def test_billing_subscription_shape(platform_client):
    resp = platform_client.get(
        "/billing/subscription",
        headers={"X-API-Key": "dev-secret-key"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["limits"]["eval_per_month"] is not None
    assert "plan_id" in body


def test_platform_slo_five_run_consistency(platform_client):
    """Cold-read consistency: same usage snapshot 5x in a row."""
    snapshots = []
    for _ in range(5):
        resp = platform_client.get(
            "/platform/usage",
            headers={"X-API-Key": "dev-secret-key"},
        )
        assert resp.status_code == 200
        snapshots.append(resp.json())
    org_ids = {s["org_id"] for s in snapshots}
    plan_ids = {s["plan_id"] for s in snapshots}
    assert len(org_ids) == 1
    assert len(plan_ids) == 1


def test_list_repositories_org_scoped(platform_client, tmp_path, monkeypatch):
    from app.config import settings
    from app.ingestion.metadata_store import metadata_store

    repos_path = tmp_path / "repos"
    repos_path.mkdir()
    monkeypatch.setattr(settings, "REPOS_PATH", str(repos_path))

    metadata_store.mark_pending("job-a", "https://github.com/a/a", "main")
    metadata_store.mark_synced("job-a", commit_hash="abc", cloned_at="2026-01-01T00:00:00Z")
    raw = metadata_store._read_raw("job-a")
    assert raw is not None
    raw["org_id"] = "default"
    metadata_store._write_raw("job-a", raw)

    metadata_store.mark_pending("job-b", "https://github.com/b/b", "main")
    metadata_store.mark_synced("job-b", commit_hash="def", cloned_at="2026-01-01T00:00:00Z")
    raw_b = metadata_store._read_raw("job-b")
    assert raw_b is not None
    raw_b["org_id"] = "other-org"
    metadata_store._write_raw("job-b", raw_b)

    resp = platform_client.get(
        "/platform/repos",
        headers={"X-API-Key": "dev-secret-key"},
    )
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["repo_id"] == "job-a"


def test_audit_includes_correlation_id(platform_client):
    platform_client.post(
        "/platform/api-keys",
        json={"label": "corr-key"},
        headers={"X-API-Key": "dev-secret-key"},
    )
    audit = platform_client.get(
        "/platform/audit",
        headers={"X-API-Key": "dev-secret-key"},
    )
    events = audit.json()
    created = [e for e in events if e.get("action") == "api_key.created"]
    assert created
    assert created[-1].get("correlation_id")


def test_platform_read_latency_budget(platform_client):
    import time

    t0 = time.perf_counter()
    resp = platform_client.get(
        "/platform/usage",
        headers={"X-API-Key": "dev-secret-key"},
    )
    elapsed = time.perf_counter() - t0
    assert resp.status_code == 200
    assert elapsed < 1.0, f"usage endpoint too slow: {elapsed:.2f}s"
