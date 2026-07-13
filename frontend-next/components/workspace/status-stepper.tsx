"use client";

import { Check, Loader2 } from "lucide-react";
import { INGEST_STEPS, ingestStepIndex } from "@/lib/constants";
import { cn } from "@/lib/utils";

export function StatusStepper({ syncStatus }: { syncStatus: string }) {
  const activeIdx = ingestStepIndex(syncStatus);
  const done = syncStatus === "synced";

  return (
    <ol
      className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6"
      aria-label="Ingestion progress"
      aria-live="polite"
    >
      {INGEST_STEPS.map((step, i) => {
        const completed = done || i < activeIdx;
        const current = !done && i === activeIdx - 1;
        return (
          <li
            key={step.key}
            className={cn(
              "flex min-h-[44px] items-center justify-center gap-1.5 rounded-lg border px-2 py-2.5 text-xs font-medium transition-colors duration-150",
              completed
                ? "border-success/30 bg-success/10 text-success"
                : current
                  ? "border-primary/40 bg-primary-muted text-foreground"
                  : "border-border bg-surface text-tertiary",
            )}
          >
            {completed ? (
              <Check className="h-3.5 w-3.5 shrink-0" aria-hidden />
            ) : current ? (
              <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" aria-hidden />
            ) : (
              <span className="h-3.5 w-3.5 shrink-0 rounded-full border border-border" aria-hidden />
            )}
            <span>{step.label}</span>
          </li>
        );
      })}
    </ol>
  );
}
