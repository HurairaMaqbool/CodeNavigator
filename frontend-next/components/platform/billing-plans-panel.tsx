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
import { cn } from "@/lib/utils";

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
        <div className="grid gap-4 sm:grid-cols-3">
          {plans.data!.map((plan) => {
            const isCurrent = plan.id === sub.plan_id;
            return (
              <div
                key={plan.id}
                className={cn(
                  "rounded-2xl border p-6 transition-all duration-300 relative overflow-hidden group flex flex-col justify-between h-full",
                  isCurrent
                    ? "border-primary bg-primary-tint/20 dark:[box-shadow:var(--shadow-2),var(--glow-primary)] shadow-elev-2"
                    : "border-border bg-surface-raised hover:border-border-strong hover:shadow-elev-1 hover:-translate-y-[1px]"
                )}
              >
                {/* Visual glow element on current plan */}
                {isCurrent && (
                  <div className="absolute right-0 top-0 h-16 w-16 bg-gradient-to-bl from-primary/10 to-transparent pointer-events-none" />
                )}
                
                <div>
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="font-display text-[15px] font-bold text-foreground">{plan.name}</h3>
                    {isCurrent && (
                      <span className="badge badge-success text-[9px] scale-90">Active</span>
                    )}
                  </div>
                  <p className="text-display mt-3 font-display">
                    {plan.price_monthly_usd === 0 ? "Free" : `$${plan.price_monthly_usd}`}
                    {plan.price_monthly_usd !== 0 && <span className="text-xs text-muted-foreground font-normal"> / mo</span>}
                  </p>
                  
                  <div className="mt-5 pt-4 border-t border-border/40 space-y-3">
                    <p className="micro-label text-[10px] text-tertiary select-none">Monthly Limits</p>
                    <ul className="space-y-2 text-xs font-mono text-muted-foreground">
                      <li className="flex justify-between">
                        <span>Chat asks</span>
                        <span className="font-semibold text-foreground">{plan.limits.chat_per_month || "Unlimited"}</span>
                      </li>
                      <li className="flex justify-between">
                        <span>Repositories</span>
                        <span className="font-semibold text-foreground">{plan.limits.ingest_per_month || "Unlimited"}</span>
                      </li>
                      <li className="flex justify-between">
                        <span>Evaluations</span>
                        <span className="font-semibold text-foreground">{plan.limits.eval_per_month || "Unlimited"}</span>
                      </li>
                    </ul>
                  </div>
                </div>
                
                <div>
                  {plan.id !== "free" && !isCurrent && (
                    <Button
                      type="button"
                      size="sm"
                      variant="accent"
                      className="mt-5 w-full flex items-center justify-center font-semibold"
                      disabled={!sub.stripe_enabled || checkout.isPending}
                      onClick={() => checkout.mutate(plan.id as "pro" | "team")}
                    >
                      {checkout.isPending ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <>
                          Upgrade plan
                          <ExternalLink className="ml-1 h-3 w-3" />
                        </>
                      )}
                    </Button>
                  )}
                  {isCurrent && (
                    <div className="mt-5 text-center py-1 bg-primary/10 rounded-lg text-xs font-semibold text-primary font-mono select-none">
                      Active Plan
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
