"use client";

import { motion } from "framer-motion";
import { useBackendOnline } from "@/lib/hooks/use-backend-health";
import { useQuery } from "@tanstack/react-query";
import {
  getBillingSubscription,
  getPlatformAudit,
  getPlatformUsage,
} from "@/lib/api";
import { AppShell } from "@/components/layout/app-shell";
import { QueryError } from "@/components/shared/empty-state";
import { SectionHeader, StatCard } from "@/components/shared/section-header";
import { Alert } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";

export default function PlatformPage() {
  const { online: backendOk, offline: backendOffline, isError: healthError } =
    useBackendOnline();

  const usage = useQuery({
    queryKey: ["usage"],
    queryFn: getPlatformUsage,
    enabled: backendOk,
  });
  const sub = useQuery({
    queryKey: ["subscription"],
    queryFn: getBillingSubscription,
    enabled: backendOk,
  });
  const audit = useQuery({
    queryKey: ["audit"],
    queryFn: () => getPlatformAudit(50),
    enabled: backendOk,
  });

  return (
    <AppShell>
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25 }}
        className="space-y-8"
      >
        <SectionHeader title="Platform" caption="Usage, billing, and audit log" />

        {backendOffline && (
          <Alert kind="warning">
            Backend offline — start uvicorn on port 8000 to load platform data.
          </Alert>
        )}

        {healthError && (
          <QueryError message="Cannot reach API" onRetry={() => window.location.reload()} />
        )}

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {usage.isLoading ? (
            <>
              <Skeleton className="h-20" />
              <Skeleton className="h-20" />
              <Skeleton className="h-20" />
              <Skeleton className="h-20" />
            </>
          ) : usage.data ? (
            <>
              <StatCard label="Org" value={usage.data.org_id} />
              <StatCard label="Plan" value={usage.data.plan_id} />
              <StatCard
                label="Chat (month)"
                value={usage.data.metrics?.chat ?? 0}
              />
              <StatCard
                label="Ingest (month)"
                value={usage.data.metrics?.ingest ?? 0}
              />
            </>
          ) : null}
        </div>

        {sub.data && (
          <details className="rounded-xl border border-border bg-surface p-4">
            <summary className="cursor-pointer font-medium text-foreground">
              Subscription details
            </summary>
            <pre className="mt-3 overflow-auto text-xs">
              {JSON.stringify(sub.data, null, 2)}
            </pre>
          </details>
        )}

        {usage.data && (
          <details className="rounded-xl border border-border bg-surface p-4">
            <summary className="cursor-pointer font-medium text-foreground">
              Usage details
            </summary>
            <pre className="mt-3 overflow-auto text-xs">
              {JSON.stringify(usage.data, null, 2)}
            </pre>
          </details>
        )}

        <div>
          <SectionHeader title="Audit log" caption="Last 50 events" />
          {audit.isLoading ? (
            <Skeleton className="h-48 w-full" />
          ) : audit.data && audit.data.length > 0 ? (
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-border bg-muted/50 text-xs uppercase text-muted-foreground">
                  <tr>
                    <th className="p-2">Time</th>
                    <th className="p-2">Action</th>
                    <th className="p-2">Actor</th>
                    <th className="p-2">Resource</th>
                  </tr>
                </thead>
                <tbody>
                  {audit.data.map((row, i) => (
                    <tr key={i} className="border-b border-border/50">
                      <td className="p-2 font-mono text-xs">{row.timestamp}</td>
                      <td className="p-2">{row.action}</td>
                      <td className="p-2">{row.actor}</td>
                      <td className="p-2 font-mono text-xs">
                        {row.resource_type}/{row.resource_id}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No audit events yet.</p>
          )}
        </div>

        <p className="text-xs text-muted-foreground">
          Admin console: http://localhost:3000
        </p>
      </motion.div>
    </AppShell>
  );
}
