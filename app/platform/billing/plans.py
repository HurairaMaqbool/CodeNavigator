"""
app/platform/billing/plans.py
-----------------------------
Subscription plan tiers and quota mapping.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.config import settings


@dataclass(frozen=True)
class Plan:
    id: str
    name: str
    price_monthly_usd: int
    chat_per_month: int
    ingest_per_month: int
    eval_per_month: int
    stripe_price_id: str = ""


def _build_plans() -> dict[str, Plan]:
    return {
        "free": Plan(
            id="free",
            name="Free",
            price_monthly_usd=0,
            chat_per_month=100,
            ingest_per_month=5,
            eval_per_month=10,
        ),
        "pro": Plan(
            id="pro",
            name="Pro",
            price_monthly_usd=49,
            chat_per_month=2000,
            ingest_per_month=50,
            eval_per_month=100,
            stripe_price_id=settings.STRIPE_PRICE_PRO or "price_pro_monthly",
        ),
        "team": Plan(
            id="team",
            name="Team",
            price_monthly_usd=199,
            chat_per_month=10000,
            ingest_per_month=200,
            eval_per_month=500,
            stripe_price_id=settings.STRIPE_PRICE_TEAM or "price_team_monthly",
        ),
    }


PLANS: dict[str, Plan] = _build_plans()


def get_plan(plan_id: str) -> Plan:
    return PLANS.get(plan_id, PLANS["free"])


def quota_for_plan(plan_id: str, metric: str) -> int:
    plan = get_plan(plan_id)
    return {
        "chat": plan.chat_per_month,
        "ingest": plan.ingest_per_month,
        "eval": plan.eval_per_month,
    }.get(metric, 0)
