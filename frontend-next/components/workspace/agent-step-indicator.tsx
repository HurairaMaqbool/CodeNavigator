"use client";

import { AGENT_STEPS, AGENT_STEP_LABELS } from "@/lib/constants";
import { cn } from "@/lib/utils";

export function AgentStepIndicator({ currentState }: { currentState: string | null }) {
  const idx = currentState
    ? AGENT_STEPS.indexOf(currentState as (typeof AGENT_STEPS)[number])
    : -1;

  return (
    <div
      className="flex flex-wrap gap-1"
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
              "rounded-full px-2 py-0.5 text-xs font-medium transition-colors",
              active
                ? "bg-primary text-primary-foreground"
                : done
                  ? "bg-success/15 text-success"
                  : "bg-muted text-muted-foreground",
            )}
          >
            {AGENT_STEP_LABELS[step] ?? step}
          </span>
        );
      })}
    </div>
  );
}
