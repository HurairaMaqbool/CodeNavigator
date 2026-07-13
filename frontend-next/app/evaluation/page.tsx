"use client";

import { useEffect, useState } from "react";
import { Loader2, Play, TestTube } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { CompareRegressionsTable } from "@/components/evaluation/compare-regressions-table";
import { useEvalAutomationOverlay } from "@/components/evaluation/eval-automation-bridge";
import { GoldenCiPanel } from "@/components/evaluation/golden-ci-panel";
import { EmptyState, QueryError } from "@/components/shared/empty-state";
import { SectionHeader, StatCard } from "@/components/shared/section-header";
import { PerQuestionDiagnostics } from "@/components/evaluation/per-question-diagnostics";
import { RagasChart } from "@/components/evaluation/ragas-chart";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useApp } from "@/lib/context/app-context";
import { useBackendOnline } from "@/lib/hooks/use-backend-health";
import { useEvalHealth } from "@/lib/hooks/use-eval-health";
import { useEvalHistory } from "@/lib/hooks/use-eval-history";
import { useEvalRunners } from "@/lib/hooks/use-eval-runners";
import { useGoldenStatus } from "@/lib/hooks/use-golden-status";
import { useRepoStatus } from "@/lib/hooks/use-repo-status";
import { pickDisplayRun } from "@/lib/eval-run-utils";
import { formatChunkSummary } from "@/lib/repo-display";
import { formatEvalRunLabel, getEvalRunKey } from "@/lib/utils";
import { cn } from "@/lib/utils";

export default function EvaluationPage() {
  const { repoId } = useApp();
  const { online: backendOk } = useBackendOnline();
  const status = useRepoStatus(repoId);
  const evalHealth = useEvalHealth(repoId, status.data);
  const history = useEvalHistory(backendOk);
  const golden = useGoldenStatus(backendOk);
  const { autoProgress, autoCompareResult, autoLastRun, autoLastRefreshAt } =
    useEvalAutomationOverlay(repoId);

  const {
    runRagas,
    runGolden,
    compare,
    ragasLoading,
    goldenLoading,
    compareLoading,
    ragasProgress,
    goldenProgress,
    lastResult,
    setLastResult,
    goldenLiveResult,
    compareResult,
    setCompareResult,
  } = useEvalRunners(repoId);

  const allRuns = history.data ?? [];
  const repoSpecificRuns = allRuns.filter((r) => r.repo_id === repoId);
  const runs = repoSpecificRuns.length > 0 ? repoSpecificRuns : allRuns;
  const [selectedRunKey, setSelectedRunKey] = useState<string | null>(null);
  const [baseline, setBaseline] = useState("");
  const [candidate, setCandidate] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 5;

  useEffect(() => {
    setLastResult(null);
    setSelectedRunKey(null);
    setCompareResult(null);
    setBaseline("");
    setCandidate("");
  }, [repoId, setLastResult, setCompareResult]);

  useEffect(() => {
    if (autoLastRun && !lastResult) {
      setLastResult(autoLastRun);
      setSelectedRunKey(getEvalRunKey(autoLastRun));
    }
  }, [autoLastRun, lastResult, setLastResult]);

  useEffect(() => {
    if (autoCompareResult && !compareResult) {
      setCompareResult(autoCompareResult);
    }
  }, [autoCompareResult, compareResult, setCompareResult]);

  const baselineVal = baseline || (runs[0] ? getEvalRunKey(runs[0]) : "");
  const candidateVal =
    candidate ||
    (runs.length > 1 ? getEvalRunKey(runs[1]) : runs[0] ? getEvalRunKey(runs[0]) : "");
  const sameSelection = baselineVal && candidateVal && baselineVal === candidateVal;

  const selectedFromHistory = selectedRunKey
    ? runs.find((r) => getEvalRunKey(r) === selectedRunKey)
    : undefined;
  const displayRun = pickDisplayRun(
    runs,
    lastResult ?? selectedFromHistory ?? null,
  );

  const evalReady = Boolean(evalHealth.data?.ok);
  const chunkSummary = formatChunkSummary(status.data, evalHealth.data);
  const effectiveRagasProgress = ragasProgress ?? autoProgress;
  const lastDataRefreshMs =
    autoLastRefreshAt ??
    (history.dataUpdatedAt > 0 ? history.dataUpdatedAt : null);
  const lastDataRefreshLabel =
    lastDataRefreshMs != null
      ? (() => {
          const mins = Math.round((Date.now() - lastDataRefreshMs) / 60_000);
          if (mins < 1) return "just now";
          if (mins < 60) return `${mins} min ago`;
          return `${Math.round(mins / 60)} hr ago`;
        })()
      : null;

  return (
    <AppShell>
      <div className="page-enter space-y-10">
        <SectionHeader
          title="Evaluation & quality assurance"
          caption={
            lastDataRefreshLabel
              ? `RAGAS metrics, version compare, and golden-set CI — auto-updates after indexing and chat (last refresh: ${lastDataRefreshLabel})`
              : "RAGAS metrics, version compare, and golden-set CI — updates automatically after indexing and chat"
          }
        />

        {autoProgress && !ragasLoading && (
          <Alert kind="info">
            Background evaluation: {autoProgress}
          </Alert>
        )}

        {!repoId ? (
          <EmptyState
            title="No repository selected"
            description="Connect and index a repository on the Connect screen first."
          />
        ) : evalHealth.isLoading ? (
          <div className="grid grid-cols-3 gap-3">
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
          </div>
        ) : evalHealth.isError ? (
          <QueryError
            message={evalHealth.error?.message ?? "Failed to load eval health"}
            onRetry={() => void evalHealth.refetch()}
          />
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-3">
              <StatCard
                label="Index"
                value={evalReady ? "Ready" : "Not ready"}
                status={evalReady ? "ok" : "warn"}
              />
              <StatCard label="Chunks" value={chunkSummary} status="neutral" />
              <StatCard
                label="Probe hits"
                value={String(evalHealth.data?.details?.probe_hit_count ?? "—")}
                status="neutral"
              />
            </div>
            {!evalReady &&
              (evalHealth.data?.errors ?? []).map((err, i) => (
                <Alert key={i} kind="error">
                  {err}
                </Alert>
              ))}
          </>
        )}

        <div className="flex flex-wrap items-center gap-3">
          <Button
            disabled={!repoId || !evalReady || ragasLoading}
            onClick={() => void runRagas()}
          >
            {ragasLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Play className="h-4 w-4" />
            )}
            Run RAGAS eval
          </Button>
          {effectiveRagasProgress && (
            <span className="text-sm text-muted-foreground flex items-center gap-1.5">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
              {effectiveRagasProgress}
            </span>
          )}
          {history.isFetching && !effectiveRagasProgress && (
            <span className="text-sm text-muted-foreground flex items-center gap-1.5">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
              Updating history...
            </span>
          )}
          <Button
            variant="secondary"
            disabled={!backendOk || goldenLoading}
            onClick={() => void runGolden()}
          >
            {goldenLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <TestTube className="h-4 w-4" />
            )}
            Run Golden CI
          </Button>
          {goldenProgress && (
            <span className="text-sm text-muted-foreground">{goldenProgress}</span>
          )}
        </div>

        {displayRun?.ragas_scores && (
          <div className="card-panel space-y-4">
            <SectionHeader
              title="RAGAS scores"
              caption={
                displayRun === lastResult
                  ? "Latest run"
                  : formatEvalRunLabel(displayRun)
              }
            />
            <div className="rounded-lg border border-info/20 bg-info/5 p-4 text-xs text-muted-foreground space-y-2">
              <p className="font-semibold text-foreground">Understanding RAG Metrics & Scores:</p>
              <ul className="list-disc pl-4 space-y-1">
                <li><strong>Golden CI (100% PASS) vs RAGAS Faithfulness</strong>: Golden CI measures source file retrieval correctness. RAGAS Faithfulness measures generation grounding (whether the AI answer is strictly supported by the retrieved context). A 100% CI pass means correct files were retrieved, but RAGAS score can drop if the LLM answers with outside knowledge.</li>
                <li><strong>Gated Status & 0.0 Confidence</strong>: Gating triggers when retrieval fails or rate limits (HTTP 429) cut off LLM queries. These fall back to safe responses.</li>
                <li><strong>Verified Confidence (Base 10.0)</strong>: Base confidence score is 10.0 and decreases only on citation syntax errors, invalid line bounds, or call-graph mismatches.</li>
              </ul>
            </div>
            <RagasChart scores={displayRun.ragas_scores} />
            {displayRun.regression_warning && (
              <Alert kind="warning" className="mt-4">
                {displayRun.regression_warning}
              </Alert>
            )}
            <PerQuestionDiagnostics run={displayRun} />
          </div>
        )}

        <div className="card-panel space-y-4">
          <SectionHeader
            title="Compare versions"
            caption="Auto-compares when a new RAGAS run completes — manual override below"
          />
          <Alert kind="info" className="mb-4">
            Chat always queries the current indexed codebase (see Active repo bar above).
            Baseline/candidate here only affect evaluation metrics comparison, not live Q&A.
          </Alert>
          {history.isLoading ? (
            <Skeleton className="mt-2 h-24 w-full" />
          ) : runs.length < 2 ? (
            <p className="text-sm text-muted-foreground">
              Run RAGAS eval at least twice to compare versions (second run triggers
              automatically after indexing).
            </p>
          ) : (
            <>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label>Baseline</Label>
                  <Select value={baselineVal} onValueChange={setBaseline}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select baseline" />
                    </SelectTrigger>
                    <SelectContent>
                      {runs.map((r) => {
                        const runKey = getEvalRunKey(r);
                        return (
                          <SelectItem key={runKey} value={runKey}>
                            {formatEvalRunLabel(r)}
                          </SelectItem>
                        );
                      })}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Candidate</Label>
                  <Select value={candidateVal} onValueChange={setCandidate}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select candidate" />
                    </SelectTrigger>
                    <SelectContent>
                      {runs.map((r) => {
                        const runKey = getEvalRunKey(r);
                        return (
                          <SelectItem key={runKey} value={runKey}>
                            {formatEvalRunLabel(r)}
                          </SelectItem>
                        );
                      })}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              {sameSelection && runs.length > 1 && (
                <Alert kind="warning" className="mt-3">
                  Pick two different runs to compare.
                </Alert>
              )}
              <Button
                className="mt-4"
                disabled={sameSelection || compareLoading}
                onClick={() => void compare(baselineVal, candidateVal)}
              >
                {compareLoading && <Loader2 className="h-4 w-4 animate-spin" />}
                Compare runs
              </Button>
              {compareResult && (
                <CompareRegressionsTable result={compareResult} />
              )}
            </>
          )}
        </div>

        <div className="card-panel space-y-4">
          <SectionHeader
            title="Golden set CI"
            caption="Refreshes automatically after each successful index (backend pipeline)"
          />
          <GoldenCiPanel
            data={golden.data}
            loading={golden.isLoading}
            liveResult={goldenLiveResult}
          />
        </div>

        {runs.length > 0 && (() => {
          const totalPages = Math.max(1, Math.ceil(runs.length / itemsPerPage));
          const paginatedRuns = runs.slice(
            (currentPage - 1) * itemsPerPage,
            currentPage * itemsPerPage
          );
          return (
            <div className="card-panel space-y-4">
              <SectionHeader
                title="Eval history"
                caption="Click a row to view RAGAS scores and per-question breakdown"
              />
              <div className="space-y-2">
                <div className="table-wrap">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Version</th>
                        <th>When</th>
                        <th>Questions</th>
                        <th>Faithfulness</th>
                      </tr>
                    </thead>
                    <tbody>
                      {paginatedRuns.map((r) => {
                        const key = getEvalRunKey(r);
                        const active = key === getEvalRunKey(displayRun ?? r);
                        return (
                          <tr
                            key={key}
                            className={cn(
                              "row-clickable",
                              active && "row-active",
                            )}
                            onClick={() => setSelectedRunKey(key)}
                          >
                            <td className="font-mono text-xs">
                              {formatEvalRunLabel(r)}
                            </td>
                            <td className="text-xs text-muted-foreground">
                              {r.timestamp
                                ? new Date(r.timestamp).toLocaleString()
                                : "—"}
                            </td>
                            <td>{r.diagnostics?.question_count ?? "—"}</td>
                            <td>
                              {r.ragas_scores?.faithfulness?.toFixed(3) ?? "—"}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                {totalPages > 1 && (
                  <div className="flex items-center justify-between border border-border bg-surface-raised px-4 py-2 rounded-lg">
                    <p className="text-xs text-muted-foreground">
                      Showing {((currentPage - 1) * itemsPerPage) + 1} to {Math.min(currentPage * itemsPerPage, runs.length)} of {runs.length} runs
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
            </div>
          );
        })()}
      </div>
    </AppShell>
  );
}
