# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/integrations/github_app/auth.py
-----------------------------------
GitHub App JWT and installation access tokens.
"""
from __future__ import annotations

import time
from typing import Any

import jwt
import requests

from app.config import settings


def app_configured() -> bool:
    return bool(
        settings.GITHUB_APP_ID
        and settings.GITHUB_APP_PRIVATE_KEY
    )


def _private_key_pem() -> str:
    key = settings.GITHUB_APP_PRIVATE_KEY or ""
    return key.replace("\\n", "\n")


def create_app_jwt() -> str:
    if not app_configured():
        raise RuntimeError("GitHub App not configured")
    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + 600,
        "iss": settings.GITHUB_APP_ID,
    }
    return jwt.encode(payload, _private_key_pem(), algorithm="RS256")


def get_installation_token(installation_id: int) -> str:
    app_jwt = create_app_jwt()
    url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["token"]


def clone_auth_header(installation_id: int | None = None) -> dict[str, str]:
    """Return Authorization header for git clone / API calls."""
    if installation_id is not None and app_configured():
        token = get_installation_token(installation_id)
        return {"Authorization": f"token {token}"}
    if settings.GITHUB_TOKEN:
        return {"Authorization": f"token {settings.GITHUB_TOKEN}"}
    return {}
