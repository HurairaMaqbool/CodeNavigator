# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""Commercial platform: billing, SSO, GitHub App."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.platform.billing.plans import PLANS, quota_for_plan
from app.platform.billing.subscriptions import get_subscription, set_subscription


def test_plans_defined():
    assert "free" in PLANS and "pro" in PLANS and "team" in PLANS
    assert quota_for_plan("pro", "chat") == 2000


def test_subscription_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("app.platform.billing.subscriptions._SUBS_PATH", tmp_path / "subs.json")
    set_subscription("acme", plan_id="pro", status="active")
    sub = get_subscription("acme")
    assert sub["plan_id"] == "pro"


def test_billing_plans_public():
    client = TestClient(app)
    resp = client.get("/billing/plans")
    assert resp.status_code == 200
    assert len(resp.json()) >= 3


def test_billing_subscription_requires_auth():
    client = TestClient(app)
    resp = client.get("/billing/subscription")
    assert resp.status_code == 401


def test_billing_subscription_authed(mock_api_key):
    client = TestClient(app)
    resp = client.get("/billing/subscription", headers={"X-API-Key": "dev-secret-key"})
    assert resp.status_code == 200
    assert "plan_id" in resp.json()


def test_auth_status():
    client = TestClient(app)
    resp = client.get("/auth/status")
    assert resp.status_code == 200
    assert "oidc_enabled" in resp.json()


def test_github_installation_registry(tmp_path, monkeypatch):
    from app.integrations.github_app.installations import (
        get_org_for_installation,
        register_installation,
    )

    monkeypatch.setattr(
        "app.integrations.github_app.installations._INSTALL_PATH",
        tmp_path / "installs.json",
    )
    register_installation(12345, org_id="acme-corp", account_login="acme")
    assert get_org_for_installation(12345) == "acme-corp"


def test_usage_meter_plan_limits(tmp_path, monkeypatch):
    from app.config import settings
    from app.platform.usage_meter import check_quota

    monkeypatch.setattr(settings, "QUOTA_CHAT_PER_MONTH", 0)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr("app.platform.billing.subscriptions._SUBS_PATH", tmp_path / "subs.json")
    monkeypatch.setattr("app.platform.usage_meter._METER_PATH", tmp_path / "meter.json")
    set_subscription("default", plan_id="free")
    assert check_quota("default", "chat") is True
