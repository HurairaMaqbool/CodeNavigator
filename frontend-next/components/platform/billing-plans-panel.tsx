"use client";

import { useState } from "react";
import { CreditCard, ExternalLink, Loader2 } from "lucide-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  createBillingCheckout,
  getBillingPlans,
  openBillingPortal,
} from "@/lib/api";
import type { SubscriptionStatus } from "@/lib/types";
import { ApiError } from "@/lib/types";
import { SectionHeader } from "@/components/shared/section-header";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

export function BillingPlansPanel({
  sub,
  enabled,
}: {
  sub: SubscriptionStatus;
  enabled: boolean;
}) {
  const plans = useQuery({
    queryKey: ["billingPlans"],
    queryFn: getBillingPlans,
    enabled,
  });

  const checkout = useMutation({
    mutationFn: (planId: "pro" | "team") => createBillingCheckout(planId),
    onSuccess: (data) => {
      if (data.checkout_url) {
        window.open(data.checkout_url, "_blank", "noopener,noreferrer");
        toast.success("Stripe checkout opened in a new tab");
      }
    },
    onError: (e) => {
      toast.error(e instanceof ApiError ? e.message : "Checkout failed");
    },
  });

  const portal = useMutation({
    mutationFn: () => openBillingPortal(),
    onSuccess: (data) => {
      if (data.portal_url) {
        window.open(data.portal_url, "_blank", "noopener,noreferrer");
        toast.success("Billing portal opened");
      }
    },
    onError: (e) => {
      toast.error(e instanceof ApiError ? e.message : "Portal unavailable");
    },
  });

  return (
    <div className="card-panel space-y-4">
      <SectionHeader
        title="Billing & plans"
        caption={`Current: ${sub.plan_name} (${sub.status})`}
      />

      {!sub.stripe_enabled && (
        <Alert kind="info">
          Billing upgrades are temporarily unavailable. Please check back later.
        </Alert>
      )}

      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          disabled={!sub.stripe_enabled || portal.isPending}
          onClick={() => portal.mutate()}
        >
          {portal.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <CreditCard className="h-4 w-4" />
          )}
          Manage subscription
        </Button>
      </div>

      {plans.isLoading ? (
        <Skeleton className="h-32 w-full" />
      ) : plans.isError ? (
        <p className="text-sm text-error">
          {plans.error instanceof ApiError ? plans.error.message : "Failed to load plans"}
        </p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-3">
          {plans.data!.map((plan) => (
            <div
              key={plan.id}
              className={`rounded-lg border p-5 transition-colors duration-150 ${
                plan.id === sub.plan_id
                  ? "border-primary bg-primary-tint shadow-elev-1"
                  : "border-border bg-surface-raised hover:border-border-strong"
              }`}
            >
              <h3 className="font-medium text-foreground">{plan.name}</h3>
              <p className="text-display mt-2">
                {plan.price_monthly_usd === 0 ? "Free" : `$${plan.price_monthly_usd}/mo`}
              </p>
              <ul className="mt-3 space-y-1 text-xs text-muted-foreground">
                <li>Chat: {plan.limits.chat_per_month || "∞"}/mo</li>
                <li>Ingest: {plan.limits.ingest_per_month || "∞"}/mo</li>
                <li>Eval: {plan.limits.eval_per_month || "∞"}/mo</li>
              </ul>
              {plan.id !== "free" && plan.id !== sub.plan_id && (
                <Button
                  type="button"
                  size="sm"
                  className="mt-3 w-full"
                  disabled={!sub.stripe_enabled || checkout.isPending}
                  onClick={() => checkout.mutate(plan.id as "pro" | "team")}
                >
                  {checkout.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <>
                      Upgrade <ExternalLink className="ml-1 h-3 w-3" />
                    </>
                  )}
                </Button>
              )}
              {plan.id === sub.plan_id && (
                <p className="mt-3 text-xs font-medium text-primary">Current plan</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
