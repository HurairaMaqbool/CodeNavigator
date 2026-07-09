# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/api/platform_router.py
--------------------------
Enterprise platform endpoints: GDPR, audit, API keys, usage.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth import verify_api_key
from app.integrations.github_app.installations import list_installations
from app.platform.api_keys import ApiKeyContext
from app.platform.api_keys import create_api_key, list_keys, revoke_api_key
from app.platform.audit_log import read_events, record_event
from app.platform.repo_purge import export_repository_data, purge_repository
from app.platform.tenant_context import get_tenant
from app.platform.usage_meter import get_usage, increment

router = APIRouter(prefix="/platform", tags=["platform"])


class CreateKeyRequest(BaseModel):
    org_id: str = Field(default="default", min_length=1, max_length=64)
    label: str = Field(default="api-key", min_length=1, max_length=128)


@router.delete("/repos/{repo_id}")
def delete_repository(repo_id: str, auth: ApiKeyContext = Depends(verify_api_key)) -> dict[str, Any]:
    """GDPR right-to-erasure: purge all data for a repository."""
    try:
        result = purge_repository(repo_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    record_event(
        "repo.purged",
        org_id=auth.org_id,
        actor=auth.label,
        resource_type="repository",
        resource_id=repo_id,
    )
    increment(auth.org_id, "purge")
    return result


@router.get("/repos/{repo_id}/export")
def export_repository(repo_id: str, auth: ApiKeyContext = Depends(verify_api_key)) -> dict[str, Any]:
    """GDPR data portability: export repository metadata snapshot."""
    try:
        return export_repository_data(repo_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/audit")
def audit_trail(limit: int = 100, auth: ApiKeyContext = Depends(verify_api_key)) -> list[dict[str, Any]]:
    return read_events(org_id=auth.org_id, limit=min(limit, 500))


@router.get("/usage")
def usage_summary(auth: ApiKeyContext = Depends(verify_api_key)) -> dict[str, Any]:
    return get_usage(auth.org_id)


@router.post("/api-keys")
def create_key(req: CreateKeyRequest, auth: ApiKeyContext = Depends(verify_api_key)) -> dict[str, str]:
    if req.org_id != auth.org_id:
        raise HTTPException(status_code=403, detail="Cannot create keys for another organization")
    secret = create_api_key(req.org_id, req.label)
    record_event("api_key.created", org_id=req.org_id, actor=auth.label, details={"label": req.label})
    return {"api_key": secret, "org_id": req.org_id, "label": req.label}


@router.get("/api-keys")
def list_api_keys(auth: ApiKeyContext = Depends(verify_api_key)) -> list[dict[str, Any]]:
    return list_keys(org_id=auth.org_id)


@router.get("/github/installations")
def github_installations(auth: ApiKeyContext = Depends(verify_api_key)) -> list[dict[str, Any]]:
    return list_installations(org_id=auth.org_id)


class RevokeKeyRequest(BaseModel):
    key_prefix: str = Field(..., min_length=4, max_length=64)


@router.delete("/api-keys")
def revoke_key(req: RevokeKeyRequest, auth: ApiKeyContext = Depends(verify_api_key)) -> dict[str, Any]:
    ok = revoke_api_key(auth.org_id, req.key_prefix)
    if not ok:
        raise HTTPException(status_code=404, detail="Key not found or already revoked")
    record_event("api_key.revoked", org_id=auth.org_id, actor=auth.label, details={"key_prefix": req.key_prefix})
    return {"status": "revoked", "key_prefix": req.key_prefix}
