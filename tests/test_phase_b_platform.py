"""Phase B/C platform: Postgres fallback, Stripe webhooks, status, keys."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.platform.api_keys import create_api_key, list_keys, resolve_api_key, revoke_api_key


def test_public_status():
    client = TestClient(app)
    resp = client.get("/status/public")
    assert resp.status_code == 200
    body = resp.json()
    assert body["overall"] in ("operational", "degraded")
    assert "components" in body


def test_stripe_price_ids_from_env(monkeypatch):
    from app.config import settings
    from app.platform.billing import plans as plans_mod

    monkeypatch.setattr(settings, "STRIPE_PRICE_PRO", "price_live_pro_123")
    monkeypatch.setattr(settings, "STRIPE_PRICE_TEAM", "price_live_team_456")
    monkeypatch.setattr(plans_mod, "PLANS", plans_mod._build_plans())
    assert plans_mod.get_plan("pro").stripe_price_id == "price_live_pro_123"
    assert plans_mod.get_plan("team").stripe_price_id == "price_live_team_456"


def test_api_key_create_and_revoke_json(tmp_path, monkeypatch):
    keys_path = tmp_path / "api_keys.json"
    monkeypatch.setattr("app.platform.api_keys._KEYS_PATH", keys_path)
    monkeypatch.setattr("app.platform.db.stores.use_postgres", lambda: False)

    secret = create_api_key("acme", "test-key")
    assert resolve_api_key(secret) is not None
    listed = list_keys("acme")
    assert len(listed) == 1
    prefix = listed[0]["key_prefix"].replace("…", "")
    assert revoke_api_key("acme", prefix)
    assert resolve_api_key(secret) is None


def test_revoke_key_endpoint(mock_api_key, tmp_path, monkeypatch):
    keys_path = tmp_path / "api_keys.json"
    monkeypatch.setattr("app.platform.api_keys._KEYS_PATH", keys_path)
    monkeypatch.setattr("app.platform.db.stores.use_postgres", lambda: False)

    client = TestClient(app)
    create_resp = client.post(
        "/platform/api-keys",
        headers={"X-API-Key": "dev-secret-key"},
        json={"label": "revoke-me"},
    )
    assert create_resp.status_code == 200
    secret = create_resp.json()["api_key"]
    prefix = secret[:8]

    revoke_resp = client.request(
        "DELETE",
        "/platform/api-keys",
        headers={"X-API-Key": "dev-secret-key"},
        json={"key_prefix": prefix},
    )
    assert revoke_resp.status_code == 200
    assert resolve_api_key(secret) is None


def test_saml_metadata_not_configured():
    client = TestClient(app)
    resp = client.get("/saml/metadata")
    assert resp.status_code == 503


def test_stripe_webhook_checkout_completed(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr("app.platform.billing.subscriptions._SUBS_PATH", tmp_path / "subs.json")
    monkeypatch.setattr("app.platform.db.stores.use_postgres", lambda: False)

    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "metadata": {"org_id": "stripe-org", "plan_id": "pro"},
                "customer": "cus_123",
                "subscription": "sub_456",
            }
        },
    }

    def fake_construct(payload, sig):
        return event

    monkeypatch.setattr(
        "app.webhook.stripe_webhook.construct_webhook_event",
        fake_construct,
    )

    client = TestClient(app)
    resp = client.post(
        "/webhook/stripe",
        content=json.dumps(event),
        headers={"stripe-signature": "sig"},
    )
    assert resp.status_code == 200
    from app.platform.billing.subscriptions import get_subscription

    sub = get_subscription("stripe-org")
    assert sub["plan_id"] == "pro"
    assert sub["stripe_customer_id"] == "cus_123"


def test_stripe_webhook_subscription_deleted(tmp_path, monkeypatch):
    from app.config import settings
    from app.platform.billing.subscriptions import get_subscription, set_subscription

    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr("app.platform.billing.subscriptions._SUBS_PATH", tmp_path / "subs.json")
    monkeypatch.setattr("app.platform.db.stores.use_postgres", lambda: False)
    set_subscription("del-org", plan_id="team", status="active")

    event = {
        "type": "customer.subscription.deleted",
        "data": {"object": {"metadata": {"org_id": "del-org"}}},
    }
    monkeypatch.setattr(
        "app.webhook.stripe_webhook.construct_webhook_event",
        lambda _p, _s: event,
    )

    client = TestClient(app)
    resp = client.post("/webhook/stripe", content=b"{}", headers={"stripe-signature": "sig"})
    assert resp.status_code == 200
    assert get_subscription("del-org")["plan_id"] == "free"
