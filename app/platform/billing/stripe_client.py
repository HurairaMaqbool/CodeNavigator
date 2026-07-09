# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/platform/billing/stripe_client.py
-------------------------------------
Stripe SDK wrapper (optional — disabled when STRIPE_SECRET_KEY unset).
"""
from __future__ import annotations

from typing import Any

from app.config import settings
from app.platform.billing.plans import PLANS, get_plan


def stripe_enabled() -> bool:
    return bool(settings.STRIPE_SECRET_KEY and settings.STRIPE_SECRET_KEY.strip())


def _stripe():
    if not stripe_enabled():
        raise RuntimeError("Stripe is not configured (set STRIPE_SECRET_KEY)")
    import stripe

    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe


def create_checkout_session(
    org_id: str,
    plan_id: str,
    *,
    success_url: str,
    cancel_url: str,
) -> dict[str, str]:
    plan = get_plan(plan_id)
    if plan.id == "free":
        raise ValueError("Cannot checkout free plan")
    if not plan.stripe_price_id:
        raise ValueError(f"Plan {plan_id} has no Stripe price configured")

    stripe = _stripe()
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": plan.stripe_price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"org_id": org_id, "plan_id": plan_id},
        subscription_data={"metadata": {"org_id": org_id, "plan_id": plan_id}},
    )
    return {"checkout_url": session.url or "", "session_id": session.id}


def create_portal_session(customer_id: str, return_url: str) -> dict[str, str]:
    stripe = _stripe()
    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )
    return {"portal_url": session.url or ""}


def construct_webhook_event(payload: bytes, sig_header: str) -> Any:
    stripe = _stripe()
    return stripe.Webhook.construct_event(
        payload, sig_header, settings.STRIPE_WEBHOOK_SECRET or ""
    )


def list_public_plans() -> list[dict[str, Any]]:
    return [
        {
            "id": p.id,
            "name": p.name,
            "price_monthly_usd": p.price_monthly_usd,
            "limits": {
                "chat_per_month": p.chat_per_month,
                "ingest_per_month": p.ingest_per_month,
                "eval_per_month": p.eval_per_month,
            },
        }
        for p in PLANS.values()
    ]
