"use client";

import { motion } from "framer-motion";
import { Check, Loader2 } from "lucide-react";
import { INGEST_STEPS, ingestStepIndex } from "@/lib/constants";
import { cn } from "@/lib/utils";

export function StatusStepper({ syncStatus }: { syncStatus: string }) {
  const activeIdx = ingestStepIndex(syncStatus);
  const done = syncStatus === "synced";

  return (
    <ol
      className="flex flex-wrap gap-2"
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
              "flex min-h-[44px] flex-1 min-w-[72px] items-center justify-center gap-1.5 rounded-lg border px-2 py-2 text-xs font-medium transition-colors",
              completed
                ? "border-success/40 bg-success/10 text-success"
                : current
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-border bg-muted/30 text-muted-foreground",
            )}
          >
            {completed ? (
              <Check className="h-3.5 w-3.5 shrink-0" aria-hidden />
            ) : current ? (
              <motion.span
                animate={{ opacity: [0.5, 1, 0.5] }}
                transition={{ duration: 1.5, repeat: Infinity }}
              >
                <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
              </motion.span>
            ) : null}
            <span>{step.label}</span>
          </li>
        );
      })}
    </ol>
  );
}
