"use client";

import { useState } from "react";
import { useBackendOnline } from "@/lib/hooks/use-backend-health";
import { useQuery } from "@tanstack/react-query";
import {
  getBillingSubscription,
  getPlatformAudit,
  getPlatformUsage,
  listGitHubInstallations,
} from "@/lib/api";
import { ApiError } from "@/lib/types";
import { AppShell } from "@/components/layout/app-shell";
import { ApiKeysPanel } from "@/components/platform/api-keys-panel";
import { AuditLogTable } from "@/components/platform/audit-log-table";
import { BillingPlansPanel } from "@/components/platform/billing-plans-panel";
import { GdprRepoPanel } from "@/components/platform/gdpr-repo-panel";
import { UsageQuotaPanel } from "@/components/platform/usage-quota-panel";
import { QueryError } from "@/components/shared/empty-state";
import { SectionHeader } from "@/components/shared/section-header";
import { Alert } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { Key, ShieldAlert, BarChart3, ListFilter } from "lucide-react";
import { cn } from "@/lib/utils";

type TabKey = "keys" | "privacy" | "quota" | "audit";

export default function PlatformPage() {
  const { online: backendOk, offline: backendOffline, isError: healthError } =
    useBackendOnline();

  const [activeTab, setActiveTab] = useState<TabKey>("keys");

  const usage = useQuery({
    queryKey: ["usage"],
    queryFn: getPlatformUsage,
    enabled: backendOk,
    retry: 3,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10000),
  });
  const sub = useQuery({
    queryKey: ["subscription"],
    queryFn: getBillingSubscription,
    enabled: backendOk,
    retry: 3,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10000),
  });
  const audit = useQuery({
    queryKey: ["audit"],
    queryFn: () => getPlatformAudit(50),
    enabled: backendOk,
    retry: 3,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10000),
  });
  const github = useQuery({
    queryKey: ["githubInstallations"],
    queryFn: listGitHubInstallations,
    enabled: backendOk,
    retry: 3,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10000),
  });

  const tabItems = [
    { key: "keys", label: "API Keys", icon: Key },
    { key: "privacy", label: "Data & Privacy", icon: ShieldAlert },
    { key: "quota", label: "Usage & Quota", icon: BarChart3 },
    { key: "audit", label: "Audit Log", icon: ListFilter },
  ] as const;

  return (
    <AppShell>
      <div className="page-enter space-y-6">
        {backendOffline && (
          <Alert kind="warning">
            Backend offline — start uvicorn on port 8000 to load platform data.
          </Alert>
        )}

        {healthError && (
          <QueryError message="Cannot reach API" onRetry={() => window.location.reload()} />
        )}

        <div className="grid grid-cols-1 md:grid-cols-12 gap-8 items-start">
          {/* Left Column: Sub-navigation card */}
          <div className="md:col-span-3 flex flex-col gap-2 rounded-xl border border-border bg-surface/30 p-3 shadow-md">
            <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider px-3 py-1 select-none">
              PLATFORM
            </span>
            <div className="flex flex-col gap-0.5 mt-1">
              {tabItems.map((item) => {
                const Icon = item.icon;
                const active = activeTab === item.key;
                return (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => setActiveTab(item.key)}
                    className={cn(
                      "flex items-center gap-3 rounded-lg px-3 py-2 text-xs font-semibold tracking-wide transition-all duration-150 cursor-pointer select-none text-left",
                      active
                        ? "bg-primary-tint text-primary"
                        : "text-muted-foreground hover:bg-surface-hover hover:text-foreground"
                    )}
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    <span>{item.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Right Column: Tab View Contents */}
          <div className="md:col-span-9 space-y-6 min-h-[500px]">
            {/* Active Tab Panel 1: API Keys */}
            {activeTab === "keys" && (
              <div className="space-y-6 animate-fade-in">
                <ApiKeysPanel enabled={backendOk} />
                
                {sub.isLoading ? (
                  <Skeleton className="h-32 w-full" />
                ) : sub.isError ? (
                  <QueryError
                    message={
                      sub.error instanceof ApiError
                        ? sub.error.message
                        : "Failed to load subscription"
                    }
                    onRetry={() => void sub.refetch()}
                  />
                ) : sub.data ? (
                  <BillingPlansPanel sub={sub.data} enabled={backendOk} />
                ) : null}
              </div>
            )}

            {/* Active Tab Panel 2: Data & Privacy */}
            {activeTab === "privacy" && (
              <div className="space-y-6 animate-fade-in">
                <GdprRepoPanel enabled={backendOk} />

                <div className="card-panel space-y-3">
                  <SectionHeader
                    title="GitHub App installations"
                    caption="Org-scoped GitHub App links (Connect tab handles repo ingest)"
                  />
                  {github.isLoading ? (
                    <Skeleton className="h-16 w-full" />
                  ) : github.isError ? (
                    <p className="text-sm text-muted-foreground">
                      {github.error instanceof ApiError
                        ? github.error.message
                        : "Could not load installations"}
                    </p>
                  ) : (github.data?.length ?? 0) === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      No GitHub App installations registered for this organization.
                    </p>
                  ) : (
                    <ul className="space-y-2 text-sm">
                      {github.data!.map((row) => (
                        <li key={row.installation_id} className="font-mono text-xs text-foreground bg-surface px-3 py-1.5 rounded-lg border border-border/40 inline-block mr-2 mb-2">
                          #{row.installation_id}
                          {row.account_login ? ` · ${row.account_login}` : ""}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            )}

            {/* Active Tab Panel 3: Usage & Quota */}
            {activeTab === "quota" && (
              <div className="space-y-6 animate-fade-in">
                {usage.isLoading ? (
                  <Skeleton className="h-40 w-full" />
                ) : usage.isError ? (
                  <QueryError
                    message={
                      usage.error instanceof ApiError
                        ? usage.error.message
                        : "Failed to load usage"
                    }
                    onRetry={() => void usage.refetch()}
                  />
                ) : usage.data ? (
                  <UsageQuotaPanel usage={usage.data} />
                ) : null}
              </div>
            )}

            {/* Active Tab Panel 4: Audit Log */}
            {activeTab === "audit" && (
              <div className="space-y-4 animate-fade-in">
                <SectionHeader title="Audit log" caption="Last 50 events (with request correlation IDs)" />
                {audit.isLoading ? (
                  <Skeleton className="h-48 w-full" />
                ) : audit.isError ? (
                  <QueryError
                    message={
                      audit.error instanceof ApiError
                        ? audit.error.message
                        : "Failed to load audit log"
                    }
                    onRetry={() => void audit.refetch()}
                  />
                ) : (
                  <AuditLogTable events={audit.data ?? []} />
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
