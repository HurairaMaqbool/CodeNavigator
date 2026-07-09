# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/webhook/stripe_webhook.py
-----------------------------
Stripe webhook handler for subscription lifecycle events.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.platform.billing.stripe_client import construct_webhook_event, stripe_enabled
from app.platform.billing.subscriptions import set_subscription

router = APIRouter()


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    if not stripe_enabled() or not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(503, "Stripe webhooks not configured")

    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = construct_webhook_event(payload, sig)
    except Exception as exc:
        raise HTTPException(400, f"Webhook signature verification failed: {exc}") from exc

    etype = event["type"]
    data = event.get("data", {}).get("object", {})

    if etype == "checkout.session.completed":
        org_id = (data.get("metadata") or {}).get("org_id", "default")
        plan_id = (data.get("metadata") or {}).get("plan_id", "pro")
        set_subscription(
            org_id,
            plan_id=plan_id,
            status="active",
            stripe_customer_id=data.get("customer"),
            stripe_subscription_id=data.get("subscription"),
        )
    elif etype in ("customer.subscription.updated", "customer.subscription.created"):
        org_id = (data.get("metadata") or {}).get("org_id", "default")
        plan_id = (data.get("metadata") or {}).get("plan_id", "pro")
        status = data.get("status", "active")
        set_subscription(
            org_id,
            plan_id=plan_id,
            status=status,
            stripe_customer_id=data.get("customer"),
            stripe_subscription_id=data.get("id"),
        )
    elif etype == "customer.subscription.deleted":
        org_id = (data.get("metadata") or {}).get("org_id", "default")
        set_subscription(org_id, plan_id="free", status="canceled")

    return JSONResponse({"received": True, "type": etype})
