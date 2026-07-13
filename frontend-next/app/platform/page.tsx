"use client";

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

export default function PlatformPage() {
  const { online: backendOk, offline: backendOffline, isError: healthError } =
    useBackendOnline();

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

  return (
    <AppShell>
      <div className="page-enter space-y-10">
        <SectionHeader
          title="Platform"
          caption="Usage, billing, API keys, GDPR, GitHub App, and audit trail"
        />

        {backendOffline && (
          <Alert kind="warning">
            Backend offline — start uvicorn on port 8000 to load platform data.
          </Alert>
        )}

        {healthError && (
          <QueryError message="Cannot reach API" onRetry={() => window.location.reload()} />
        )}

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

        <ApiKeysPanel enabled={backendOk} />

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
                <li key={row.installation_id} className="font-mono text-xs">
                  #{row.installation_id}
                  {row.account_login ? ` · ${row.account_login}` : ""}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="space-y-3">
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
      </div>
    </AppShell>
  );
}
