import type { CompareResult } from "@/lib/types";

function RegressionTable({ result }: { result: CompareResult }) {
  if (!result.regressions_found || result.regressions.length === 0) {
    return (
      <p className="text-sm text-success">
        No regressions within tolerance.
      </p>
    );
  }

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Metric</th>
            <th>Baseline</th>
            <th>Candidate</th>
            <th>Delta</th>
            <th>Kind</th>
          </tr>
        </thead>
        <tbody>
          {result.regressions.map((row, i) => (
            <tr key={i}>
              <td className="font-mono text-xs">{row.metric}</td>
              <td>{row.baseline_value.toFixed(4)}</td>
              <td>{row.new_value.toFixed(4)}</td>
              <td className="text-error">{row.delta.toFixed(4)}</td>
              <td className="text-xs text-muted-foreground">{row.kind}</td>
            </tr>
          ))}
        </tbody>
      </table>
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
        <p className="text-sm text-warning">
          {result.index_version_warning}
        </p>
      )}
      <RegressionTable result={result} />
    </div>
  );
}
