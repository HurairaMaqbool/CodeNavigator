# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/api/billing_router.py
-------------------------
Stripe billing: plans, checkout, portal, subscription status.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.auth import verify_api_key
from app.platform.api_keys import ApiKeyContext
from app.platform.billing import stripe_client
from app.platform.billing.plans import get_plan
from app.platform.billing.subscriptions import get_subscription, set_subscription

router = APIRouter(prefix="/billing", tags=["billing"])


class CheckoutRequest(BaseModel):
    plan_id: str = Field(..., pattern="^(pro|team)$")
    success_url: str = Field(default="http://localhost:8501")
    cancel_url: str = Field(default="http://localhost:8501")


@router.get("/plans")
def list_plans() -> list[dict[str, Any]]:
    return stripe_client.list_public_plans()


@router.get("/subscription")
def subscription_status(auth: ApiKeyContext = Depends(verify_api_key)) -> dict[str, Any]:
    sub = get_subscription(auth.org_id)
    plan = get_plan(sub["plan_id"])
    return {
        **sub,
        "plan_name": plan.name,
        "limits": {
            "chat_per_month": plan.chat_per_month,
            "ingest_per_month": plan.ingest_per_month,
            "eval_per_month": plan.eval_per_month,
        },
        "stripe_enabled": stripe_client.stripe_enabled(),
    }


@router.post("/checkout")
def create_checkout(req: CheckoutRequest, auth: ApiKeyContext = Depends(verify_api_key)) -> dict[str, str]:
    if not stripe_client.stripe_enabled():
        raise HTTPException(
            status_code=503,
            detail="Stripe not configured. Set STRIPE_SECRET_KEY and price IDs in .env",
        )
    try:
        return stripe_client.create_checkout_session(
            auth.org_id,
            req.plan_id,
            success_url=req.success_url,
            cancel_url=req.cancel_url,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/portal")
def customer_portal(
    return_url: str = "http://localhost:8501",
    auth: ApiKeyContext = Depends(verify_api_key),
) -> dict[str, str]:
    if not stripe_client.stripe_enabled():
        raise HTTPException(status_code=503, detail="Stripe not configured")
    sub = get_subscription(auth.org_id)
    customer_id = sub.get("stripe_customer_id")
    if not customer_id:
        raise HTTPException(status_code=404, detail="No Stripe customer for this org")
    return stripe_client.create_portal_session(customer_id, return_url)
