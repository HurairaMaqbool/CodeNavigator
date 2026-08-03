# Copyright (c) 2026 Huraira Maqbool
# Systematic Whitebox Testing Suite — exercising boundary conditions & unhandled error paths.

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# ---------------------------------------------------------------------------
# 1. Security: Path Jail Traversal
# ---------------------------------------------------------------------------
from app.security.path_jail import resolve_jailed_path, PathJailError, normalize_repo_relative_path

def test_whitebox_path_jail_traversal_escapes():
    root = Path("/tmp/fake_repo_root").resolve()
    
    # Standard parent traversal
    with pytest.raises(PathJailError):
        resolve_jailed_path(root, "../../etc/passwd")

    # Mixed Windows/POSIX separators
    with pytest.raises(PathJailError):
        resolve_jailed_path(root, "..\\../etc/passwd")

    # UNC path prefix
    with pytest.raises(PathJailError):
        resolve_jailed_path(root, "\\\\attacker\\share\\payload")

def test_whitebox_path_jail_normalize_prefix():
    assert normalize_repo_relative_path("repos/abc1234/clone/src/main.py") == "src/main.py"
    assert normalize_repo_relative_path("repos/abc1234/clone/app/agent/loop.py") == "app/agent/loop.py"


# ---------------------------------------------------------------------------
# 2. Security: OIDC Token Verification Audience/Issuer
# ---------------------------------------------------------------------------
from app.auth.oidc_jwks import verify_id_token

@patch("app.auth.oidc_jwks._get_jwks_client")
@patch("jwt.decode")
def test_whitebox_oidc_issuer_verification_configured(mock_jwt_decode, mock_jwks):
    mock_client = MagicMock()
    mock_client.get_signing_key_from_jwt.return_value.key = "fake_pubkey"
    mock_jwks.return_value = mock_client
    
    with patch("app.config.settings.ENVIRONMENT", "production"):
        with patch("app.config.settings.OIDC_ALLOW_UNSIGNED", False):
            with patch("app.config.settings.OIDC_CLIENT_ID", "test-client-id"):
                try:
                    verify_id_token("fake.jwt.token")
                except Exception:
                    pass
                
                assert mock_jwt_decode.called
                kwargs = mock_jwt_decode.call_args[1]
                assert kwargs.get("audience") == "test-client-id"


# ---------------------------------------------------------------------------
# 3. Ingestion: ZIP Fallback URL Parsing for SSH URLs
# ---------------------------------------------------------------------------
from app.ingestion.clone import _parse_github_url, InvalidURLError

def test_whitebox_parse_github_url_ssh():
    owner, repo = _parse_github_url("https://github.com/psf/requests.git")
    assert owner == "psf" and repo == "requests"
    
    owner, repo = _parse_github_url("git@github.com:psf/requests.git")
    assert owner == "psf" and repo == "requests"
    
    owner, repo = _parse_github_url("ssh://git@github.com/psf/requests.git")
    assert owner == "psf" and repo == "requests"


# ---------------------------------------------------------------------------
# 4. Core Logic: claim_verification check_claim_keywords_present boolean return
# ---------------------------------------------------------------------------
from app.agent.claim_verification import check_claim_keywords_present

def test_whitebox_check_claim_keywords_present_returns_bool():
    res_true = check_claim_keywords_present("authentication token", "this file manages authentication token validation")
    assert res_true is True

    res_false = check_claim_keywords_present("cryptographic signature", "this file manages database connections")
    assert res_false is False


# ---------------------------------------------------------------------------
# 5. Data Integrity: Usage Meter Quotas
# ---------------------------------------------------------------------------
from app.platform.usage_meter import increment, get_usage, check_quota

def test_whitebox_usage_meter_increment_and_quota(tmp_path):
    with patch("app.platform.usage_meter._METER_PATH", tmp_path / "usage_meter.json"):
        with patch("app.platform.usage_meter._use_pg", return_value=False):
            with patch("app.config.settings.ENVIRONMENT", "production"):
                with patch("app.config.settings.QUOTA_CHAT_PER_MONTH", 5):
                    res1 = increment("test_org", "chat", 1)
                    assert res1.get("chat") == 1
                    
                    assert check_quota("test_org", "chat") is True
                    
                    increment("test_org", "chat", 4)
                    assert check_quota("test_org", "chat") is False
