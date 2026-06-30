"""Phase A commercial hardening tests."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.auth.oauth_state import clear_memory_states, consume_state, create_state, store_state
from app.integrations.github_app.clone_auth import authenticated_https_url, zip_download_headers
from app.integrations.github_app.installations import add_repo_to_installation, register_installation


def test_oauth_state_one_time_use():
    clear_memory_states()
    state = create_state()
    assert consume_state(state) is True
    assert consume_state(state) is False


def test_oauth_state_redis_fallback(monkeypatch):
    clear_memory_states()
    monkeypatch.setattr("app.redis_client.get_redis", lambda: None)
    store_state("test-state-xyz")
    assert consume_state("test-state-xyz") is True


def test_zip_headers_include_pat(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "GITHUB_TOKEN", "ghp_testtoken")
    monkeypatch.setattr(
        "app.integrations.github_app.clone_auth.resolve_installation_id",
        lambda _url: None,
    )
    headers = zip_download_headers("https://github.com/org/private-repo")
    assert "Authorization" in headers


def test_authenticated_url_embeds_token(monkeypatch):
    monkeypatch.setattr(
        "app.integrations.github_app.clone_auth.auth_headers_for_repo",
        lambda _url: {"Authorization": "token ghp_secret"},
    )
    url = authenticated_https_url("https://github.com/org/repo")
    assert "x-access-token:ghp_secret@" in url


def test_add_repo_to_installation(tmp_path, monkeypatch):
    path = tmp_path / "installs.json"
    monkeypatch.setattr("app.integrations.github_app.installations._INSTALL_PATH", path)
    register_installation(99, org_id="acme", account_login="acme")
    add_repo_to_installation(99, "acme/private-api")
    from app.integrations.github_app.installations import get_installation_for_repo

    assert get_installation_for_repo("acme/private-api") == 99


def test_create_key_blocks_cross_org(mock_api_key):
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    resp = client.post(
        "/platform/api-keys",
        json={"org_id": "other-org", "label": "hack"},
        headers={"X-API-Key": "dev-secret-key"},
    )
    assert resp.status_code == 403


def test_oidc_unsigned_only_when_allowed(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "OIDC_ALLOW_UNSIGNED", False)
    monkeypatch.setattr(settings, "OIDC_CLIENT_ID", "client")

    with patch("app.auth.oidc_jwks._get_jwks_client") as mock_jwks:
        mock_jwks.side_effect = RuntimeError("should use jwks")
        from app.auth.oidc_jwks import verify_id_token

        with pytest.raises(RuntimeError):
            verify_id_token("invalid.jwt.token")
