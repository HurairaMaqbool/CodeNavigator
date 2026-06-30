"""
app/api/sso_router.py
---------------------
OIDC SSO login, callback, logout, and session info.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.auth.oidc import (
    authorization_url,
    create_session_token,
    decode_session_token,
    exchange_code,
    oidc_enabled,
)
from app.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
def login():
    if not oidc_enabled():
        raise HTTPException(503, "OIDC SSO not configured")
    url, _state = authorization_url()
    return RedirectResponse(url)


@router.get("/callback")
def callback(code: str = Query(...), state: str = Query(...)):
    if not oidc_enabled():
        raise HTTPException(503, "OIDC SSO not configured")
    try:
        user = exchange_code(code, state)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
    token = create_session_token(user)
    redirect = settings.OIDC_POST_LOGIN_REDIRECT or "http://localhost:3000"
    response = RedirectResponse(f"{redirect}?token={token}")
    response.set_cookie(
        "session_token",
        token,
        httponly=True,
        secure=settings.ENVIRONMENT.lower() == "production",
        samesite="lax",
        max_age=settings.SESSION_TTL_SECONDS,
    )
    return response


@router.post("/logout")
def logout():
    response = JSONResponse({"status": "logged_out"})
    response.delete_cookie("session_token")
    return response


@router.get("/me")
def session_info(request: Request, session_token: str | None = None) -> dict[str, Any]:
    token = session_token or request.cookies.get("session_token") or ""
    claims = decode_session_token(token)
    if not claims:
        raise HTTPException(401, "Not authenticated")
    return {
        "sub": claims.get("sub"),
        "email": claims.get("email"),
        "name": claims.get("name"),
        "org_id": claims.get("org_id", "default"),
    }


@router.get("/status")
def auth_status() -> dict[str, Any]:
    return {"oidc_enabled": oidc_enabled()}
