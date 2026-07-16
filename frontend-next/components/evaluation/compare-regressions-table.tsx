"use client";

import { useState } from "react";
import { ArrowDown, ArrowUp, ChevronRight, Minus } from "lucide-react";
import { cn } from "@/lib/utils";
import type { CompareResult } from "@/lib/types";

type FilterMode = "all" | "regressions" | "improved";

interface RegressionRow {
  metric: string;
  baseline_value: number;
  new_value: number;
  delta: number;
  kind: string;
}

function DeltaPill({ delta }: { delta: number }) {
  const isRegression = delta < -0.001;
  const isImprovement = delta > 0.001;

  if (isRegression) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-destructive/15 px-2 py-0.5 text-[10px] font-mono font-semibold text-destructive">
        <ArrowDown className="h-2.5 w-2.5" />
        {delta.toFixed(4)}
      </span>
    );
  }
  if (isImprovement) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-success/15 px-2 py-0.5 text-[10px] font-mono font-semibold text-success">
        <ArrowUp className="h-2.5 w-2.5" />
        +{delta.toFixed(4)}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-surface-elevated px-2 py-0.5 text-[10px] font-mono text-muted-foreground">
      <Minus className="h-2.5 w-2.5" />
      {delta.toFixed(4)}
    </span>
  );
}

function FilterPills({
  mode,
  onChange,
}: {
  mode: FilterMode;
  onChange: (m: FilterMode) => void;
}) {
  const pills: { label: string; value: FilterMode }[] = [
    { label: "All", value: "all" },
    { label: "Regressions", value: "regressions" },
    { label: "Improved", value: "improved" },
  ];
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[10px] uppercase tracking-widest text-muted-foreground mr-1">
        Show:
      </span>
      {pills.map((p) => (
        <button
          key={p.value}
          type="button"
          onClick={() => onChange(p.value)}
          className={cn(
            "rounded-full border px-2.5 py-0.5 text-[11px] font-medium transition-all duration-150",
            mode === p.value
              ? "border-primary/50 bg-accent text-primary"
              : "border-border/60 text-muted-foreground hover:border-primary/30 hover:bg-surface-hover hover:text-foreground"
          )}
        >
          {p.label}
        </button>
      ))}
    </div>
  );
}

function RegressionTable({ result }: { result: CompareResult }) {
  const [filter, setFilter] = useState<FilterMode>("all");

  if (!result.regressions_found || result.regressions.length === 0) {
    return (
      <p className="text-sm text-success flex items-center gap-2">
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-success" />
        No regressions within tolerance.
      </p>
    );
  }

  const rows = result.regressions.filter((row: RegressionRow) => {
    if (filter === "regressions") return row.delta < -0.001;
    if (filter === "improved") return row.delta > 0.001;
    return true;
  });

  return (
    <div className="space-y-3">
      <FilterPills mode={filter} onChange={setFilter} />
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Metric</th>
              <th>Baseline</th>
              <th>Candidate</th>
              <th>Delta</th>
              <th>Kind</th>
              <th className="w-8" />
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td
                  colSpan={6}
                  className="py-6 text-center text-sm text-muted-foreground"
                >
                  No rows match this filter.
                </td>
              </tr>
            ) : (
              rows.map((row: RegressionRow, i: number) => {
                const isRegression = row.delta < -0.001;
                return (
                  <tr
                    key={i}
                    className={cn(
                      "group cursor-pointer transition-all duration-150",
                      "hover:bg-surface-hover",
                      isRegression && "bg-destructive/5 hover:bg-destructive/10"
                    )}
                  >
                    <td className="font-mono text-xs">{row.metric}</td>
                    <td className="font-mono text-xs tabular-nums">
                      {row.baseline_value.toFixed(4)}
                    </td>
                    <td className="font-mono text-xs tabular-nums">
                      {row.new_value.toFixed(4)}
                    </td>
                    <td>
                      <DeltaPill delta={row.delta} />
                    </td>
                    <td className="text-xs text-muted-foreground">{row.kind}</td>
                    <td className="opacity-0 group-hover:opacity-100 transition-opacity">
                      <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function CompareRegressionsTable({
  result,
}: {
  result: CompareResult;
}) {
  if (result.incomparable) {
    return (
      <p className="mt-3 text-sm text-warning">
        {result.incomparable_reason ??
          "These runs cannot be compared (different eval configurations)."}
      </p>
    );
  }

  if (result.first_run_baseline_established) {
    return (
      <p className="mt-3 text-sm text-muted-foreground">
        First run — baseline established for future comparisons.
      </p>
    );
  }

  return (
    <div className="mt-4 space-y-3">
      {result.index_version_warning && (
        <p className="text-sm text-warning">{result.index_version_warning}</p>
      )}
      <RegressionTable result={result} />
    </div>
  );
}
