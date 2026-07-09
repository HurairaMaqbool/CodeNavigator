# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/auth/oidc.py
----------------
OIDC login flow (Google, Okta, Azure AD compatible).
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx

from app.auth.oauth_state import consume_state, create_state
from app.auth.oidc_jwks import verify_id_token
from app.config import settings


def oidc_enabled() -> bool:
    return bool(
        settings.OIDC_CLIENT_ID
        and settings.OIDC_CLIENT_SECRET
        and settings.OIDC_ISSUER_URL
    )


def _issuer() -> str:
    return (settings.OIDC_ISSUER_URL or "").rstrip("/")


def authorization_url(state: str | None = None) -> tuple[str, str]:
    if not oidc_enabled():
        raise RuntimeError("OIDC not configured")
    state = state or create_state()
    params = {
        "client_id": settings.OIDC_CLIENT_ID,
        "response_type": "code",
        "scope": settings.OIDC_SCOPES,
        "redirect_uri": settings.OIDC_REDIRECT_URI,
        "state": state,
    }
    url = f"{_issuer()}/authorize?{urlencode(params)}"
    return url, state


def exchange_code(code: str, state: str) -> dict[str, Any]:
    if not consume_state(state):
        raise ValueError("Invalid or expired OAuth state")

    token_url = f"{_issuer()}/oauth/token"
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.OIDC_REDIRECT_URI,
        "client_id": settings.OIDC_CLIENT_ID,
        "client_secret": settings.OIDC_CLIENT_SECRET,
    }
    resp = httpx.post(token_url, data=data, timeout=15)
    resp.raise_for_status()
    tokens = resp.json()

    id_token = tokens.get("id_token")
    if not id_token:
        raise ValueError("No id_token in OIDC response")

    claims = verify_id_token(id_token)
    return {
        "sub": claims.get("sub", ""),
        "email": claims.get("email", ""),
        "name": claims.get("name", ""),
        "org_id": _org_from_claims(claims),
        "access_token": tokens.get("access_token"),
    }


def _org_from_claims(claims: dict[str, Any]) -> str:
    for key in ("org_id", "organization", "hd", "tenant"):
        val = claims.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()[:64]
    email = claims.get("email", "")
    if isinstance(email, str) and "@" in email:
        domain = email.split("@", 1)[1].split(".")[0]
        return domain[:64] or "default"
    return "default"


def create_session_token(user: dict[str, Any]) -> str:
    import jwt
    import time

    secret = settings.SESSION_SECRET or settings.API_KEY
    now = int(time.time())
    payload = {
        "sub": user.get("sub"),
        "email": user.get("email"),
        "name": user.get("name"),
        "org_id": user.get("org_id", "default"),
        "iat": now,
        "exp": now + settings.SESSION_TTL_SECONDS,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_session_token(token: str) -> dict[str, Any] | None:
    import jwt

    secret = settings.SESSION_SECRET or settings.API_KEY
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except Exception:
        return None
