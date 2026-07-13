# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/integrations/github_app/clone_auth.py
-----------------------------------------
Resolve GitHub credentials for cloning (App installation or PAT).
"""
from __future__ import annotations

from urllib.parse import urlparse

from app.config import settings
from app.integrations.github_app.auth import clone_auth_header
from app.integrations.github_app.installations import get_installation_for_repo, list_installations


def _owner_repo_from_url(repo_url: str) -> tuple[str, str]:
    clean = repo_url.rstrip("/").replace(".git", "")
    if clean.startswith("git@"):
        # git@github.com:owner/repo
        path = clean.split(":", 1)[-1]
        parts = path.split("/")
        return parts[0], parts[1]
    parsed = urlparse(clean)
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        raise ValueError(f"Cannot parse owner/repo from {repo_url!r}")
    return parts[0], parts[1]


def resolve_installation_id(repo_url: str) -> int | None:
    owner, repo = _owner_repo_from_url(repo_url)
    full_name = f"{owner}/{repo}"
    inst = get_installation_for_repo(full_name)
    if inst is not None:
        return inst
    # Match installation by account login (org/user that installed the app)
    for rec in list_installations():
        login = (rec.get("account_login") or "").lower()
        if login and login == owner.lower():
            return int(rec["installation_id"])
    return None


def auth_headers_for_repo(repo_url: str) -> dict[str, str]:
    installation_id = resolve_installation_id(repo_url)
    return clone_auth_header(installation_id)


def authenticated_https_url(repo_url: str) -> str:
    """
    Return HTTPS clone URL with embedded token when credentials exist.
    GitHub accepts: https://x-access-token:TOKEN@github.com/owner/repo
    """
    if not repo_url.startswith("https://github.com"):
        return repo_url
    headers = auth_headers_for_repo(repo_url)
    auth = headers.get("Authorization", "")
    if not auth.lower().startswith("token ") and not auth.lower().startswith("bearer "):
        return repo_url
    token = auth.split(" ", 1)[1].strip()
    return repo_url.replace("https://", f"https://x-access-token:{token}@", 1)


def zip_download_headers(repo_url: str) -> dict[str, str]:
    headers = {
        "User-Agent": "codenavigator/1.0",
        "Accept": "application/vnd.github+json",
    }
    headers.update(auth_headers_for_repo(repo_url))
    if settings.GITHUB_TOKEN and "Authorization" not in headers:
        headers["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"
    return headers
