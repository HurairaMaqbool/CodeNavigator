"use client";

import { AGENT_STEPS, AGENT_STEP_LABELS } from "@/lib/constants";
import { cn } from "@/lib/utils";

export function AgentStepIndicator({
  currentState,
}: {
  currentState: string | null;
}) {
  const idx = currentState
    ? AGENT_STEPS.indexOf(currentState as (typeof AGENT_STEPS)[number])
    : -1;

  return (
    <div
      className="flex flex-wrap gap-1.5"
      aria-label="Agent progress"
      aria-live="polite"
    >
      {AGENT_STEPS.map((step, i) => {
        const active = step === currentState;
        const done = idx >= 0 && i < idx;
        return (
          <span
            key={step}
            className={cn(
              "rounded-md border px-2 py-0.5 text-[11px] font-medium transition-colors duration-150",
              active
                ? "border-primary/40 bg-primary-muted text-foreground"
                : done
                  ? "border-success/25 bg-success/10 text-success"
                  : "border-border bg-surface text-tertiary",
            )}
          >
            {AGENT_STEP_LABELS[step] ?? step}
          </span>
        );
      })}
    </div>
  );
}
