import { useState } from "react";
import type { EvalRun, PerQuestionDiagnostic } from "@/lib/types";
import { SectionHeader, StatCard } from "@/components/shared/section-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

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
  const itemsPerPage = 10;
  const totalPages = Math.max(1, Math.ceil(rows.length / itemsPerPage));
  const paginatedRows = rows.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  );

  // Reconcile mean precision at 3 from aggregate or diagnostics
  const precisionVal =
    run.retrieval_precision_at_3 != null
      ? run.retrieval_precision_at_3.toFixed(2)
      : diag?.mean_precision_at_3 != null
      ? diag.mean_precision_at_3.toFixed(2)
      : "—";

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
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Hit</th>
                  <th>P@3</th>
                  <th>Gated</th>
                  <th>Conf</th>
                  <th>State OK</th>
                  <th>Top files</th>
                  <th>Question</th>
                </tr>
              </thead>
              <tbody>
                {paginatedRows.map((row, i) => {
                  const globalIdx = (currentPage - 1) * itemsPerPage + i;
                  return (
                    <tr key={globalIdx}>
                      <td>{globalIdx + 1}</td>
                      <td>
                        <StatusBadge ok={rowHit(row)} />
                      </td>
                      <td>{row.precision_at_3?.toFixed(2) ?? "—"}</td>
                      <td>
                        {row.gated ? (
                          <Badge variant="warning">Gated</Badge>
                        ) : (
                          <Badge variant="muted">Open</Badge>
                        )}
                      </td>
                      <td>{rowConfidence(row)?.toFixed(1) ?? "—"}</td>
                      <td>
                        <StatusBadge ok={row.state_path_consistent} />
                      </td>
                      <td className="max-w-[160px] truncate font-mono text-xs text-muted-foreground">
                        {(row.top_files ?? row.expected_files ?? row.ground_truth_files ?? [])
                          .slice(0, 3)
                          .join(", ") || "—"}
                      </td>
                      <td className="max-w-xs truncate font-mono text-xs">{row.question}</td>
                    </tr>
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
