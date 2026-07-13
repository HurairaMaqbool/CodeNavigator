import type { GoldenStatus } from "@/lib/types";
import { SectionHeader, StatCard } from "@/components/shared/section-header";
import { Alert } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";

function formatAge(seconds?: number): string {
  if (seconds == null) return "";
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
}

export function GoldenCiPanel({
  data,
  loading,
  liveResult,
}: {
  data?: GoldenStatus;
  loading?: boolean;
  liveResult?: GoldenStatus | null;
}) {
  const status = liveResult ?? data;

  if (loading && !status) {
    return <Skeleton className="h-16 w-full" />;
  }

  if (!status || status.status === "not_yet_run") {
    return (
      <p className="text-sm text-muted-foreground">
        Golden CI has not run yet. Click &quot;Run Golden CI&quot; or complete a
        repo ingest (runs automatically after indexing).
      </p>
    );
  }

  const failed = status.failed_questions ?? [];
  const failedDetails = status.failed_details ?? [];
  const perRepo = status.per_repo ?? [];

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard
          label="Status"
          value={status.status.toUpperCase()}
          status={
            status.status === "pass"
              ? "ok"
              : status.status === "fail"
                ? "error"
                : "warn"
          }
        />
        <StatCard
          label="Score"
          value={
            status.score != null ? `${Math.round(status.score * 100)}%` : "—"
          }
          status={
            status.score != null && status.score >= 0.9
              ? "ok"
              : status.score != null && status.score >= 0.7
                ? "warn"
                : "error"
          }
        />
        <StatCard
          label="Passed"
          value={`${status.passed ?? "—"}/${status.total ?? "—"}`}
        />
      </div>

      {status.timestamp && (
        <p className="text-xs text-muted-foreground">
          Last run: {new Date(status.timestamp).toLocaleString()}
          {status.age_seconds != null && ` (${formatAge(status.age_seconds)})`}
          {status.stale && " · stale — re-run recommended"}
        </p>
      )}

      {(status.skipped_fixtures?.length ?? 0) > 0 && (
        <Alert kind="warning">
          Skipped fixtures (repo not indexed):{" "}
          {status.skipped_fixtures!.join(", ")}
        </Alert>
      )}

      {perRepo.length > 0 && (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Fixture</th>
                <th>Passed</th>
                <th>Score</th>
              </tr>
            </thead>
            <tbody>
              {perRepo.map((row) => (
                <tr key={row.fixture}>
                  <td className="font-mono text-xs">{row.fixture}</td>
                  <td>
                    {row.passed}/{row.total}
                  </td>
                  <td>
                    {row.score != null
                      ? `${Math.round(row.score * 100)}%`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {failedDetails.length > 0 ? (
        <div>
          <SectionHeader title="Failed questions" />
          <div className="mt-2 table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Fixture</th>
                  <th>Expected</th>
                  <th>Cited</th>
                  <th>Question</th>
                </tr>
              </thead>
              <tbody>
                {failedDetails.map((row) => (
                  <tr key={row.question}>
                    <td className="font-mono text-xs">{row.fixture ?? "—"}</td>
                    <td className="max-w-[140px] font-mono text-xs">
                      {(row.expected_files ?? []).join(", ") || "—"}
                    </td>
                    <td className="max-w-[140px] font-mono text-xs text-muted-foreground">
                      {(row.cited_files ?? []).slice(0, 3).join(", ") ||
                        row.error ||
                        "—"}
                    </td>
                    <td className="max-w-xs font-mono text-xs">{row.question}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : failed.length > 0 ? (
        <div>
          <SectionHeader title="Failed questions" />
          <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-muted-foreground">
            {failed.map((q) => (
              <li key={q} className="font-mono text-xs">
                {q}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
