"""
app/auth/oidc_jwks.py
---------------------
Fetch OIDC provider JWKS and verify ID tokens.
"""
from __future__ import annotations

import time
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient

from app.config import settings

_JWKS_CLIENT: PyJWKClient | None = None
_JWKS_CACHE_AT = 0.0


def _issuer() -> str:
    return (settings.OIDC_ISSUER_URL or "").rstrip("/")


def _get_jwks_client() -> PyJWKClient:
    global _JWKS_CLIENT, _JWKS_CACHE_AT
    now = time.time()
    if _JWKS_CLIENT is None or now - _JWKS_CACHE_AT > 3600:
        jwks_uri = f"{_issuer()}/.well-known/openid-configuration"
        resp = httpx.get(jwks_uri, timeout=10)
        resp.raise_for_status()
        jwks_url = resp.json().get("jwks_uri") or f"{_issuer()}/oauth/certs"
        _JWKS_CLIENT = PyJWKClient(jwks_url, cache_keys=True)
        _JWKS_CACHE_AT = now
    return _JWKS_CLIENT


def verify_id_token(id_token: str) -> dict[str, Any]:
    """
    Verify OIDC id_token signature and standard claims.
    Falls back to unsigned decode only when ENVIRONMENT != production and
    OIDC_ALLOW_UNSIGNED=true (local dev with mock IdP).
    """
    if settings.ENVIRONMENT.lower() == "production" or not settings.OIDC_ALLOW_UNSIGNED:
        client = _get_jwks_client()
        signing_key = client.get_signing_key_from_jwt(id_token)
        return jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=settings.OIDC_CLIENT_ID,
            options={"verify_aud": bool(settings.OIDC_CLIENT_ID)},
        )
    return jwt.decode(id_token, options={"verify_signature": False})
