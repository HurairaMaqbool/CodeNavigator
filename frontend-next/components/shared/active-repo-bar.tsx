"use client";

import Link from "next/link";
import { useApp } from "@/lib/context/app-context";
import { useRepoStatus } from "@/lib/hooks/use-repo-status";
import { useEvalHealth } from "@/lib/hooks/use-eval-health";
import { formatChunkSummary, formatIndexState } from "@/lib/repo-display";
import { truncateId } from "@/lib/utils";
import { cn } from "@/lib/utils";

export function ActiveRepoBar() {
  const { repoId } = useApp();
  const status = useRepoStatus(repoId);
  const evalHealth = useEvalHealth(repoId, status.data);

  if (!repoId) {
    return (
      <div className="mb-6 flex items-center justify-between gap-3 rounded-lg border border-dashed border-border bg-surface/50 px-4 py-3 text-sm">
        <span className="text-muted-foreground">No repository connected</span>
        <Link
          href="/onboarding"
          className="text-sm font-medium text-primary hover:text-primary-hover transition-colors"
        >
          Connect a repo →
        </Link>
      </div>
    );
  }

  const { label, ready, syncing } = formatIndexState(status.data, evalHealth.data);
  const chunks = formatChunkSummary(status.data, evalHealth.data);
  const evalWarn = evalHealth.data && !evalHealth.data.ok && ready;

  return (
    <div
      className="mb-6 flex flex-wrap items-center gap-x-6 gap-y-2 rounded-lg border border-border bg-surface px-4 py-3 shadow-elev-1"
      role="status"
      aria-live="polite"
    >
      <div className="flex items-center gap-2">
        <span className="micro-label">Repository</span>
        <span className="font-mono text-xs text-foreground">{truncateId(repoId)}</span>
      </div>
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "h-2 w-2 rounded-full",
            ready ? "bg-success" : syncing ? "bg-warning" : "bg-tertiary",
          )}
          aria-hidden
        />
        <span className="text-sm text-foreground">Index · {label}</span>
      </div>
      <span className="text-sm text-muted-foreground">
        <span className="text-tertiary">Chunks</span>{" "}
        <span className="font-medium tabular-nums text-foreground">{chunks}</span>
      </span>
      {evalWarn && (
        <span className="text-sm text-warning">Eval precheck needs attention</span>
      )}
    </div>
  );
}
