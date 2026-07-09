# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/api/auth.py
---------------
API key authentication with multi-tenant context.
Supports X-API-Key header or session_token cookie (OIDC SSO).
"""
from __future__ import annotations

from fastapi import HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from app.auth.oidc import decode_session_token
from app.platform.api_keys import ApiKeyContext, resolve_api_key
from app.platform.tenant_context import set_tenant

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    request: Request,
    key: str | None = Security(api_key_header),
) -> ApiKeyContext:
    if key:
        ctx = resolve_api_key(key)
        if ctx is not None:
            set_tenant(ctx.org_id, api_key_label=ctx.label)
            return ctx

    session = request.cookies.get("session_token") or request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if session:
        claims = decode_session_token(session)
        if claims:
            org_id = claims.get("org_id", "default")
            label = claims.get("email") or claims.get("name") or "sso"
            set_tenant(org_id, api_key_label=label)
            return ApiKeyContext(org_id=org_id, label=label, key_id="sso")

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API Key",
    )
