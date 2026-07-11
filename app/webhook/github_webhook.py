# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/webhook/github_webhook.py
-----------------------------
GitHub Webhook Integration for auto-reingestion.

Responsibility boundary
-----------------------
Verifies HMAC signatures and delegates valid `push` events to the existing
ingestion orchestrator. 
It does NOT:
  - implement its own clone or locking mechanism
  - respond to non-push events
"""
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.api.rate_limiter import limiter
from app.config import settings
from app.observability.logging_config import logger
from app.api.router import trigger_ingest
from app.webhook.delivery_guard import is_duplicate_delivery
from tenacity import retry, stop_after_attempt, wait_exponential

router = APIRouter()


def verify_hmac_signature(payload_body: bytes, signature_header: str | None, secret: str | None) -> None:
    """
    Verify the GitHub HMAC-SHA256 signature against the raw payload bytes.
    
    Why compare_digest?
    -------------------
    A naive `==` string comparison is vulnerable to a timing attack that can leak 
    the expected signature byte by byte. `hmac.compare_digest` runs in constant time.
    """
    if not secret:
        raise HTTPException(500, "Webhook secret is not configured on the server")
    if not signature_header:
        raise HTTPException(401, "Missing X-Hub-Signature-256 header")
        
    expected = "sha256=" + hmac.new(secret.encode(), payload_body, hashlib.sha256).hexdigest()
    
    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(401, "Invalid webhook signature")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _safe_trigger_ingest(repo_url: str, branch: str, bg_tasks: BackgroundTasks):
    return trigger_ingest(repo_url=repo_url, ref=branch, force_reindex=False, bg_tasks=bg_tasks)


@router.post("/webhook/github")
@limiter.limit(settings.WEBHOOK_RATE_LIMIT)
async def github_webhook(
    request: Request,
    bg_tasks: BackgroundTasks,
    x_hub_signature_256: str | None = Header(None),
    x_github_delivery: str | None = Header(None),
):
    body = await request.body()

    verify_hmac_signature(body, x_hub_signature_256, settings.effective_webhook_secret())

    if is_duplicate_delivery(x_github_delivery):
        logger.info("webhook_duplicate_delivery", delivery_id=x_github_delivery)
        return JSONResponse(
            status_code=200,
            content={"status": "ignored", "reason": "duplicate delivery"},
        )
    
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON payload")

    event = request.headers.get("X-GitHub-Event")
    log = logger.bind(event=event, delivery_id=x_github_delivery)

    if event != "push":
        log.info("webhook_ignored", reason="not a push event")
        return {"status": "ignored", "reason": "not a push event"}

    # Defensively check structure to avoid 500s on malformed hooks
    if "ref" not in payload or "repository" not in payload or "default_branch" not in payload["repository"] or "clone_url" not in payload["repository"]:
        raise HTTPException(400, "Malformed push payload structure")

    branch = payload["ref"].split("/")[-1]
    default_branch = payload["repository"]["default_branch"]
    
    if branch != default_branch:
        log.info("webhook_ignored", reason="non-default branch", branch=branch)
        return {"status": "ignored", "reason": f"push to non-default branch ({branch})"}

    repo_url = payload["repository"]["clone_url"]
    
    # Duplicate commit hash check
    commit_hash = payload.get("after")
    if commit_hash:
        from app.ingestion.clone import repo_id_for
        from app.ingestion.metadata_store import Stage, metadata_store
        
        provisional_id = repo_id_for(repo_url, branch)
        meta = metadata_store.get(provisional_id)
        if not meta or Stage.is_pending(meta.sync_status):
            alias_id = metadata_store.get_alias(provisional_id)
            if alias_id:
                meta = metadata_store.get(alias_id)
                
        if meta and meta.commit_hash == commit_hash and Stage.is_synced(meta.sync_status):
            log.info("webhook_ignored", reason="commit already ingested", commit=commit_hash)
            return {"status": "ignored", "reason": f"Commit {commit_hash} is already fully ingested"}

    # We call the safe trigger wrapper which retries on transient errors
    job = _safe_trigger_ingest(repo_url, branch, bg_tasks)
    
    log.info("webhook_triggered_ingest", repo_url=repo_url, branch=branch, job_id=job.job_id, status=job.status)
    return {"status": "accepted", "job_id": job.job_id, "ingest_status": job.status}
