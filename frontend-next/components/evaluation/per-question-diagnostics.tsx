"use client";

import { useState, Fragment } from "react";
import type { EvalRun, PerQuestionDiagnostic } from "@/lib/types";
import { SectionHeader, StatCard } from "@/components/shared/section-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ChevronDown, ChevronUp, Info, HelpCircle } from "lucide-react";
import { cn } from "@/lib/utils";

function rowHit(row: PerQuestionDiagnostic): boolean {
  return Boolean(row.hit ?? row.gt_hit);
}

function rowConfidence(row: PerQuestionDiagnostic): number | undefined {
  return row.confidence ?? row.confidence_score;
}

function StatusBadge({
  ok,
  label,
}: {
  ok: boolean | undefined;
  label?: string;
}) {
  if (ok === undefined) {
    return <span className="text-muted-foreground">—</span>;
  }
  return (
    <Badge variant={ok ? "success" : "error"}>
      {label ?? (ok ? "Yes" : "No")}
    </Badge>
  );
}

type SortField = "hit" | "precision" | "gated" | "confidence" | "consistent" | "question" | null;
type SortDirection = "asc" | "desc";

export function PerQuestionDiagnostics({
  run,
  title = "Per-question breakdown",
}: {
  run: EvalRun;
  title?: string;
}) {
  const rows: PerQuestionDiagnostic[] = run.per_question ?? [];
  const diag = run.diagnostics;

  const [currentPage, setCurrentPage] = useState(1);
  const [sortField, setSortField] = useState<SortField>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");
  const [expandedRows, setExpandedRows] = useState<Record<number, boolean>>({});

  const itemsPerPage = 10;

  // Toggle row expansion
  const toggleRow = (index: number) => {
    setExpandedRows((prev) => ({
      ...prev,
      [index]: !prev[index],
    }));
  };

  // Sorting handler
  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDirection("asc");
    }
  };

  // Sort rows
  const sortedRows = [...rows].sort((a, b) => {
    if (!sortField) return 0;

    let aVal: any = "";
    let bVal: any = "";

    switch (sortField) {
      case "hit":
        aVal = rowHit(a) ? 1 : 0;
        bVal = rowHit(b) ? 1 : 0;
        break;
      case "precision":
        aVal = a.precision_at_3 ?? 0;
        bVal = b.precision_at_3 ?? 0;
        break;
      case "gated":
        aVal = a.gated ? 1 : 0;
        bVal = b.gated ? 1 : 0;
        break;
      case "confidence":
        aVal = rowConfidence(a) ?? 0;
        bVal = rowConfidence(b) ?? 0;
        break;
      case "consistent":
        aVal = a.state_path_consistent ? 1 : 0;
        bVal = b.state_path_consistent ? 1 : 0;
        break;
      case "question":
        aVal = a.question || "";
        bVal = b.question || "";
        break;
    }

    if (aVal < bVal) return sortDirection === "asc" ? -1 : 1;
    if (aVal > bVal) return sortDirection === "asc" ? 1 : -1;
    return 0;
  });

  const totalPages = Math.max(1, Math.ceil(sortedRows.length / itemsPerPage));
  const paginatedRows = sortedRows.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  );

  // Reconcile mean precision at 3
  const precisionVal =
    run.retrieval_precision_at_3 != null
      ? run.retrieval_precision_at_3.toFixed(2)
      : diag?.mean_precision_at_3 != null
      ? diag.mean_precision_at_3.toFixed(2)
      : "—";

  const renderSortArrow = (field: SortField) => {
    if (sortField !== field) return null;
    return sortDirection === "asc" ? (
      <ChevronUp className="inline h-3 w-3 ml-0.5" />
    ) : (
      <ChevronDown className="inline h-3 w-3 ml-0.5" />
    );
  };

  return (
    <div className="space-y-4">
      <SectionHeader title={title} />
      {diag && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard label="Questions" value={diag.question_count ?? rows.length} />
          <StatCard label="Gated" value={diag.gated_count ?? "—"} />
          <StatCard label="Mean P@3" value={precisionVal} />
          <StatCard label="Version" value={run.version ?? "—"} />
        </div>
      )}
      {rows.length > 0 ? (
        <div className="space-y-2">
          <div className="table-wrap max-h-[500px] overflow-y-auto relative rounded-lg border border-border/40">
            <table className="data-table w-full border-collapse">
              <thead className="sticky top-0 bg-surface-raised z-20 shadow-[0_1px_0_0_rgba(255,255,255,0.1)]">
                <tr>
                  <th className="w-8">#</th>
                  <th className="cursor-pointer select-none" onClick={() => handleSort("hit")}>
                    Hit {renderSortArrow("hit")}
                  </th>
                  <th className="cursor-pointer select-none" onClick={() => handleSort("precision")}>
                    P@3 {renderSortArrow("precision")}
                  </th>
                  <th className="cursor-pointer select-none" onClick={() => handleSort("gated")}>
                    Gated {renderSortArrow("gated")}
                  </th>
                  <th className="cursor-pointer select-none" onClick={() => handleSort("confidence")}>
                    Conf {renderSortArrow("confidence")}
                  </th>
                  <th className="cursor-pointer select-none" onClick={() => handleSort("consistent")}>
                    State OK {renderSortArrow("consistent")}
                  </th>
                  <th>Top files</th>
                  <th className="cursor-pointer select-none" onClick={() => handleSort("question")}>
                    Question {renderSortArrow("question")}
                  </th>
                  <th className="w-8" />
                </tr>
              </thead>
              <tbody>
                {paginatedRows.map((row, i) => {
                  const globalIdx = (currentPage - 1) * itemsPerPage + i;
                  const isExpanded = expandedRows[globalIdx];
                  const confidence = rowConfidence(row);
                  const isGated = row.gated;

                  return (
                    <Fragment key={globalIdx}>
                      <tr
                        className={cn(
                          "row-clickable cursor-pointer transition-colors duration-150 hover:bg-surface-hover/80",
                          isExpanded && "bg-surface-hover"
                        )}
                        onClick={() => toggleRow(globalIdx)}
                      >
                        <td>{globalIdx + 1}</td>
                        <td>
                          <StatusBadge ok={rowHit(row)} />
                        </td>
                        <td className="font-mono text-xs tabular-nums text-right">
                          {row.precision_at_3 != null ? row.precision_at_3.toFixed(2) : "—"}
                        </td>
                        <td>
                          {isGated ? (
                            <Badge className="bg-primary/10 text-primary border-none hover:bg-primary/20">Gated</Badge>
                          ) : (
                            <Badge variant="muted">Open</Badge>
                          )}
                        </td>
                        <td className="font-mono text-xs tabular-nums text-right">
                          {isGated ? (
                            <span
                              className="text-muted-foreground cursor-help flex items-center justify-end gap-1"
                              title="Confidence unavailable — query was gated before scoring"
                            >
                              0.0
                              <HelpCircle className="h-3 w-3 opacity-60" />
                            </span>
                          ) : confidence != null ? (
                            confidence.toFixed(2)
                          ) : (
                            "—"
                          )}
                        </td>
                        <td>
                          <StatusBadge ok={row.state_path_consistent} />
                        </td>
                        <td
                          className="max-w-[160px] truncate font-mono text-xs text-muted-foreground"
                          title={(row.top_files ?? row.expected_files ?? row.ground_truth_files ?? []).join(", ")}
                        >
                          {(row.top_files ?? row.expected_files ?? row.ground_truth_files ?? [])
                            .slice(0, 3)
                            .join(", ") || "—"}
                        </td>
                        <td
                          className="max-w-xs truncate font-mono text-xs"
                          title={row.question}
                        >
                          {row.question}
                        </td>
                        <td>
                          {isExpanded ? (
                            <ChevronUp className="h-4 w-4 text-muted-foreground" />
                          ) : (
                            <ChevronDown className="h-4 w-4 text-muted-foreground" />
                          )}
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr className="bg-surface-elevated/40 border-l border-r border-border/30">
                          <td colSpan={9} className="p-4">
                            <div className="space-y-3 text-xs leading-relaxed">
                              <div>
                                <p className="font-semibold text-muted-foreground mb-1">Full Question</p>
                                <p className="font-mono bg-surface p-2.5 rounded-lg border border-border/40 text-foreground">
                                  {row.question}
                                </p>
                              </div>
                              <div className="grid grid-cols-2 gap-4">
                                <div>
                                  <p className="font-semibold text-muted-foreground mb-1">Expected Ground Truth Files</p>
                                  <div className="font-mono bg-surface p-2.5 rounded-lg border border-border/40 text-foreground space-y-1">
                                    {(row.expected_files ?? row.ground_truth_files ?? []).length > 0 ? (
                                      (row.expected_files ?? row.ground_truth_files ?? []).map((f) => <div key={f}>{f}</div>)
                                    ) : (
                                      <span className="text-muted-foreground">None specified</span>
                                    )}
                                  </div>
                                </div>
                                <div>
                                  <p className="font-semibold text-muted-foreground mb-1">Top Retrieved Files</p>
                                  <div className="font-mono bg-surface p-2.5 rounded-lg border border-border/40 text-foreground space-y-1">
                                    {(row.top_files ?? []).length > 0 ? (
                                      (row.top_files ?? []).map((f) => <div key={f}>{f}</div>)
                                    ) : (
                                      <span className="text-muted-foreground">None retrieved</span>
                                    )}
                                  </div>
                                </div>
                              </div>
                              {(row as any).answer && (
                                <div>
                                  <p className="font-semibold text-muted-foreground mb-1">Generated Response</p>
                                  <p className="font-mono bg-surface p-2.5 rounded-lg border border-border/40 text-foreground max-h-40 overflow-y-auto whitespace-pre-wrap">
                                    {(row as any).answer}
                                  </p>
                                </div>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between border border-border bg-surface-raised px-4 py-2 rounded-lg">
              <p className="text-xs text-muted-foreground">
                Showing {((currentPage - 1) * itemsPerPage) + 1} to {Math.min(currentPage * itemsPerPage, rows.length)} of {rows.length} questions
              </p>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs px-2"
                  disabled={currentPage === 1}
                  onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                >
                  Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs px-2"
                  disabled={currentPage === totalPages}
                  onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
                >
                  Next
                </Button>
              </div>
            </div>
          )}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">No per-question breakdown available.</p>
      )}
    </div>
  );
}
