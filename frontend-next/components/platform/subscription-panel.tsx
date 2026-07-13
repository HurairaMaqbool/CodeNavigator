"use client";

import type { SubscriptionStatus } from "@/lib/types";
import { SectionHeader, StatCard } from "@/components/shared/section-header";
import { Alert } from "@/components/ui/alert";

export function SubscriptionPanel({ sub }: { sub: SubscriptionStatus }) {
  return (
    <div className="card-panel space-y-4">
      <SectionHeader title="Subscription" caption={sub.plan_name} />
      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard label="Plan ID" value={sub.plan_id} />
        <StatCard label="Status" value={sub.status} />
        <StatCard
          label="Stripe"
          value={sub.stripe_enabled ? "Connected" : "Not configured"}
        />
      </div>
      {!sub.stripe_enabled && (
        <Alert kind="info">
          Billing checkout is disabled until Stripe keys are set in backend .env.
        </Alert>
      )}
      <div className="grid gap-4 sm:grid-cols-3 text-sm">
        <div>
          <p className="micro-label">Chat limit</p>
          <p className="mt-1 text-foreground">{sub.limits.chat_per_month || "Unlimited"}</p>
        </div>
        <div>
          <p className="micro-label">Ingest limit</p>
          <p className="mt-1 text-foreground">{sub.limits.ingest_per_month || "Unlimited"}</p>
        </div>
        <div>
          <p className="micro-label">Eval limit</p>
          <p className="mt-1 text-foreground">{sub.limits.eval_per_month || "Unlimited"}</p>
        </div>
      </div>
    </div>
  );
}
