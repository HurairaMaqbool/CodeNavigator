"""
app/webhook/github_app_webhook.py
---------------------------------
GitHub App webhook events (installation, push, repository).
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.api.rate_limiter import limiter
from app.config import settings
from app.integrations.github_app.installations import (
    get_org_for_installation,
    register_installation,
    remove_installation,
)
from app.observability.logging_config import logger
from app.platform.tenant_context import set_tenant
from app.webhook.delivery_guard import is_duplicate_delivery
from app.webhook.github_webhook import verify_hmac_signature

router = APIRouter()


@router.post("/webhook/github-app")
@limiter.limit(settings.WEBHOOK_RATE_LIMIT)
async def github_app_webhook(
    request: Request,
    bg_tasks: BackgroundTasks,
    x_hub_signature_256: str | None = Header(None),
    x_github_event: str | None = Header(None),
    x_github_delivery: str | None = Header(None),
):
    secret = settings.effective_webhook_secret()
    if not secret:
        raise HTTPException(500, "Webhook secret not configured")

    body = await request.body()
    verify_hmac_signature(body, x_hub_signature_256, secret)

    if is_duplicate_delivery(x_github_delivery):
        return JSONResponse({"status": "ignored", "reason": "duplicate delivery"})

    try:
        payload: dict[str, Any] = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON payload")

    event = (x_github_event or "").lower()
    installation = payload.get("installation") or {}
    installation_id = installation.get("id")

    if event == "installation":
        action = payload.get("action", "")
        account = (installation.get("account") or {}).get("login", "")
        if action == "created":
            org_id = account.lower().replace(" ", "-")[:64] or "default"
            register_installation(
                int(installation_id),
                org_id=org_id,
                account_login=account,
            )
            logger.info("github_app_installed", installation_id=installation_id, org_id=org_id)
        elif action == "deleted" and installation_id:
            remove_installation(int(installation_id))
        return JSONResponse({"status": "ok", "event": event})

    if event == "push" and installation_id:
        from app.integrations.github_app.installations import add_repo_to_installation

        org_id = get_org_for_installation(int(installation_id))
        set_tenant(org_id)
        repo = payload.get("repository") or {}
        full_name = repo.get("full_name")
        if full_name:
            add_repo_to_installation(int(installation_id), full_name)
        repo_url = repo.get("html_url") or repo.get("clone_url")
        ref = (payload.get("ref") or "").replace("refs/heads/", "")
        default_branch = repo.get("default_branch", "main")
        if ref and ref != default_branch:
            return JSONResponse({"status": "ignored", "reason": "non-default branch"})
        if repo_url:
            from app.api.router import trigger_ingest

            trigger_ingest(repo_url=repo_url, ref=default_branch, force_reindex=False, bg_tasks=bg_tasks)
        return JSONResponse({"status": "accepted", "org_id": org_id})

    return JSONResponse({"status": "ignored", "event": event})
