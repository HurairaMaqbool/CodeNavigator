import type { EvalRun, PerQuestionDiagnostic } from "@/lib/types";
import { SectionHeader, StatCard } from "@/components/shared/section-header";

export function PerQuestionDiagnostics({
  run,
  title = "Per-question breakdown",
}: {
  run: EvalRun;
  title?: string;
}) {
  const rows: PerQuestionDiagnostic[] = run.per_question ?? [];
  const diag = run.diagnostics;

  return (
    <div className="space-y-4">
      <SectionHeader title={title} />
      {diag && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard label="Questions" value={diag.question_count ?? rows.length} />
          <StatCard label="Gated" value={diag.gated_count ?? "—"} />
          <StatCard
            label="Mean P@3"
            value={
              diag.mean_precision_at_3 != null
                ? diag.mean_precision_at_3.toFixed(2)
                : "—"
            }
          />
          <StatCard label="Version" value={run.version ?? "—"} />
        </div>
      )}
      {rows.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border bg-muted/50 text-xs uppercase text-muted-foreground">
              <tr>
                <th className="p-2">#</th>
                <th className="p-2">Hit</th>
                <th className="p-2">P@3</th>
                <th className="p-2">Gated</th>
                <th className="p-2">Conf</th>
                <th className="p-2">Question</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i} className="border-b border-border/50">
                  <td className="p-2">{i + 1}</td>
                  <td className="p-2">{row.hit ? "✅" : "❌"}</td>
                  <td className="p-2">
                    {row.precision_at_3?.toFixed(2) ?? "—"}
                  </td>
                  <td className="p-2">{row.gated ? "Yes" : "No"}</td>
                  <td className="p-2">
                    {row.confidence?.toFixed(2) ?? "—"}
                  </td>
                  <td className="max-w-xs truncate p-2 font-mono text-xs">
                    {row.question}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
