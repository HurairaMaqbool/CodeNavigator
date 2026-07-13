"use client";

import type { UsageSummary } from "@/lib/types";
import { SectionHeader, StatCard } from "@/components/shared/section-header";

function quotaLabel(used: number, limit: number): string {
  if (limit <= 0) return `${used} (unlimited)`;
  return `${used} / ${limit}`;
}

function quotaPct(used: number, limit: number): number {
  if (limit <= 0) return 0;
  return Math.min(100, Math.round((used / limit) * 100));
}

export function UsageQuotaPanel({ usage }: { usage: UsageSummary }) {
  const metrics = [
    { key: "chat", label: "Chat" },
    { key: "ingest", label: "Ingest" },
    { key: "eval", label: "Eval" },
  ] as const;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <SectionHeader title="Usage this month" caption={`${usage.month} · ${usage.subscription_status}`} className="mb-0" />
        <span className="text-xs font-medium text-warning bg-warning/10 border border-warning/20 px-2 py-1 rounded-md">
          Soft Limits: Enforcement paused in non-production
        </span>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Organization" value={usage.org_id} />
        <StatCard label="Plan" value={usage.plan_id} />
        {metrics.map(({ key, label }) => (
          <StatCard
            key={key}
            label={`${label} (month)`}
            value={quotaLabel(usage.metrics?.[key] ?? 0, usage.limits?.[`${key}_per_month`] ?? 0)}
          />
        ))}
      </div>
      <div className="card-surface space-y-3 p-6">
        {metrics.map(({ key, label }) => {
          const used = usage.metrics?.[key] ?? 0;
          const limit = usage.limits?.[`${key}_per_month`] ?? 0;
          const pct = quotaPct(used, limit);
          return (
            <div key={key}>
              <div className="mb-1 flex justify-between text-xs text-muted-foreground">
                <span>{label}</span>
                <span>{limit > 0 ? `${pct}%` : "no cap"}</span>
              </div>
              {limit > 0 && (
                <div className="h-2 overflow-hidden rounded-full bg-muted">
                  <div
                    className={`h-full rounded-full transition-[width] duration-300 ease-out ${pct >= 90 ? "bg-error" : "bg-primary"}`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
