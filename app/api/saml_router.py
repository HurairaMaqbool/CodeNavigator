"""
app/api/saml_router.py
----------------------
Enterprise SAML SSO entry points (metadata + login redirect).
Uses IdP metadata URL when configured; falls back to OIDC login.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from app.config import settings

router = APIRouter(prefix="/saml", tags=["saml"])


def saml_enabled() -> bool:
    return bool(
        settings.SAML_ENABLED
        and settings.SAML_IDP_METADATA_URL
        and settings.SAML_SP_ENTITY_ID
    )


@router.get("/metadata")
def sp_metadata() -> dict[str, Any]:
    if not saml_enabled():
        raise HTTPException(503, "SAML not configured")
    acs = settings.SAML_ACS_URL or f"{settings.OIDC_REDIRECT_URI.rsplit('/auth', 1)[0]}/saml/acs"
    return {
        "entity_id": settings.SAML_SP_ENTITY_ID,
        "assertion_consumer_service_url": acs,
        "idp_metadata_url": settings.SAML_IDP_METADATA_URL,
        "note": "Full SAML assertion parsing requires python3-saml; use OIDC for MVP.",
    }


@router.get("/login")
def saml_login():
    if saml_enabled():
        raise HTTPException(
            501,
            "SAML SP-initiated login: configure python3-saml and SAML_ACS handler. "
            "Use /auth/login for OIDC meanwhile.",
        )
    from app.auth.oidc import authorization_url, oidc_enabled
    if oidc_enabled():
        url, _ = authorization_url()
        return RedirectResponse(url)
    raise HTTPException(503, "Neither SAML nor OIDC configured")
