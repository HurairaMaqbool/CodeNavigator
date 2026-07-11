"use client";

import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import { repoIsReady } from "@/lib/constants";
import type { IngestStatusResponse } from "@/lib/types";
import { QueryError } from "@/components/shared/empty-state";
import { SectionHeader, StatCard } from "@/components/shared/section-header";
import { Alert } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusStepper } from "./status-stepper";

export function StatusPanel({
  data,
  isLoading,
  isError,
  error,
  onRetry,
}: {
  data?: IngestStatusResponse;
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
  onRetry: () => void;
}) {
  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-32" />
        <Skeleton className="h-24 w-full" />
        <div className="grid grid-cols-2 gap-3">
          <Skeleton className="h-20" />
          <Skeleton className="h-20" />
        </div>
      </div>
    );
  }

  if (isError) {
    return <QueryError message={error?.message ?? "Unknown error"} onRetry={onRetry} />;
  }

  if (!data) return null;

  const ready = repoIsReady(data);
  const failed = data.status === "failed";

  let statusLabel = "Indexing";
  let StatusIcon: typeof CheckCircle2 = CheckCircle2;
  let statusClass = "text-warning";

  if (ready) {
    statusLabel = "Ready";
    StatusIcon = CheckCircle2;
    statusClass = "text-success";
  } else if (failed) {
    statusLabel = "Failed";
    StatusIcon = XCircle;
    statusClass = "text-error";
  } else {
    StatusIcon = AlertTriangle;
  }

  return (
    <div className="space-y-4">
      <SectionHeader title="Repository status" caption="Live indexing progress" />
      <div
        className={`flex items-center gap-2 text-sm font-medium ${statusClass}`}
        role="status"
      >
        <StatusIcon className="h-4 w-4" aria-hidden />
        {statusLabel}
        <span className="text-muted-foreground">· {data.sync_status}</span>
      </div>

      <StatusStepper syncStatus={data.sync_status} />

      {ready ? (
        <div className="grid grid-cols-2 gap-3">
          <StatCard label="Files" value={data.files_parsed} />
          <StatCard label="Chunks" value={data.chunks_created} />
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          {failed
            ? "Indexing did not complete."
            : `${data.files_parsed} files · ${data.chunks_created} chunks so far`}
        </p>
      )}

      {failed && data.error_reason && (
        <Alert kind="error">{data.error_reason}</Alert>
      )}

      {data.graph_truncated && (
        <Alert kind="warning">Call graph was truncated for this repo.</Alert>
      )}

      {data.has_circular_dependencies && (
        <p className="text-xs text-muted-foreground">
          Circular dependencies detected in the dependency graph.
        </p>
      )}
    </div>
  );
}
