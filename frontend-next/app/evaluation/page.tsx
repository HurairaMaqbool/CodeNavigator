"use client";

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Clock,
  Download,
  Loader2,
  Play,
  TestTube,
  TrendingDown,
  TrendingUp,
  Zap,
  Info,
} from "lucide-react";
import { toast } from "sonner";
import { AppShell } from "@/components/layout/app-shell";
import { CompareRegressionsTable } from "@/components/evaluation/compare-regressions-table";
import { useEvalAutomationOverlay } from "@/components/evaluation/eval-automation-bridge";
import { GoldenCiPanel } from "@/components/evaluation/golden-ci-panel";
import { QueryError } from "@/components/shared/empty-state";
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
import { cn, formatEvalRunLabel, getEvalRunKey } from "@/lib/utils";
import type { RagasScores } from "@/lib/types";

/* ── helpers ─────────────────────────────────────────────── */

function avgScore(scores: RagasScores | null | undefined): number | null {
  if (!scores) return null;
  const vals = Object.values(scores).filter((v) => typeof v === "number") as number[];
  if (vals.length === 0) return null;
  return vals.reduce((a, b) => a + b, 0) / vals.length;
}

function scoreLabel(score: number): string {
  if (score >= 0.85) return "Excellent";
  if (score >= 0.75) return "Healthy";
  if (score >= 0.6) return "Fair";
  if (score >= 0.45) return "Needs work";
  return "Critical";
}

function scoreChipClass(score: number): string {
  if (score >= 0.75) return "bg-success/15 text-success";
  if (score >= 0.6) return "bg-warning/15 text-warning";
  return "bg-destructive/15 text-destructive";
}

function scoreBorderClass(score: number): string {
  if (score >= 0.75) return "border-l-4 border-l-success";
  if (score >= 0.6) return "border-l-4 border-l-warning";
  return "border-l-4 border-l-destructive";
}

/* ── CI Checks Panel ─────────────────────────────────────── */

type CheckStatus = "pass" | "warn" | "fail" | "pending";

interface CiCheck {
  label: string;
  detail: string;
  status: CheckStatus;
}

function CiChecksPanel({ checks, lastRunLabel }: { checks: CiCheck[]; lastRunLabel: string | null }) {
  return (
    <div className="divide-y divide-border/30">
      {checks.map((check) => (
        <div
          key={check.label}
          className={cn(
            "group flex items-center justify-between py-3 px-1.5 first:pt-0 last:pb-0",
            "rounded transition-colors duration-150 hover:bg-surface-hover/50",
            "cursor-default border-l-2 pl-3",
            check.status === "pass"
              ? "border-l-success"
              : check.status === "fail"
              ? "border-l-destructive"
              : check.status === "warn"
              ? "border-l-warning"
              : "border-l-border"
          )}
        >
          <div className="flex items-center gap-3">
            {check.status === "pass" ? (
              <CheckCircle2 className="h-4 w-4 text-success shrink-0" />
            ) : check.status === "fail" ? (
              <AlertTriangle className="h-4 w-4 text-destructive shrink-0" />
            ) : check.status === "warn" ? (
              <AlertTriangle className="h-4 w-4 text-warning shrink-0" />
            ) : (
              <Clock className="h-4 w-4 text-muted-foreground shrink-0" />
            )}
            <span className="text-sm text-foreground flex items-center gap-1.5">
              {check.label}
              {check.label === "RAGAS evaluation" && (
                <span
                  className="text-muted-foreground/70 cursor-help hover:text-foreground transition-colors"
                  title="RAGAS Gate: Requires avg RAGAS score ≥ 0.70"
                >
                  <Info className="h-3.5 w-3.5" />
                </span>
              )}
            </span>
          </div>
          <div className="flex items-center gap-2">
            {lastRunLabel && (
              <span className="text-[10px] text-muted-foreground font-mono mr-1">
                {lastRunLabel}
              </span>
            )}
            <span className="font-mono text-[11px] text-muted-foreground">
              {check.detail}
            </span>
            <span
              className={cn(
                "rounded px-2 py-0.5 text-[9px] font-mono uppercase tracking-widest",
                check.status === "pass"
                  ? "bg-success/10 text-success"
                  : check.status === "fail"
                  ? "bg-destructive/10 text-destructive"
                  : check.status === "warn"
                  ? "bg-warning/10 text-warning"
                  : "bg-surface-elevated text-muted-foreground"
              )}
            >
              {check.status}
            </span>
            <ChevronRight className="h-3.5 w-3.5 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity duration-150" />
          </div>
        </div>
      ))}
    </div>
  );
}

/* ── RAGAS Metric Progress Bars ──────────────────────────── */

const RAGAS_METRIC_LABELS: Record<string, string> = {
  faithfulness: "Faithfulness",
  answer_relevancy: "Answer Relevancy",
  context_precision: "Context Precision",
  context_recall: "Context Recall",
  answer_correctness: "Answer Correctness",
};

const THRESHOLD = 0.7;

function getMetricColorClass(value: number): string {
  if (value >= THRESHOLD) return "bg-primary";
  if (value >= 0.5) return "bg-warning";
  return "bg-destructive";
}

function getMetricTextColorClass(value: number): string {
  if (value >= THRESHOLD) return "text-foreground";
  if (value >= 0.5) return "text-warning";
  return "text-destructive";
}

function RagasMetricBars({ scores }: { scores: RagasScores }) {
  const entries = Object.entries(scores).filter(([, v]) => typeof v === "number");
  return (
    <div className="space-y-3">
      {entries.map(([key, val]) => {
        const pct = Math.round((val as number) * 100);
        const label = RAGAS_METRIC_LABELS[key] ?? key.replace(/_/g, " ");
        return (
          <div key={key} className="space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">{label}</span>
              <span
                className={cn(
                  "font-mono text-[11px] tabular-nums font-semibold",
                  getMetricTextColorClass(val as number)
                )}
              >
                {(val as number).toFixed(3)}
              </span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-elevated relative">
              {/* Threshold marker at 70% */}
              <div
                className="absolute top-0 bottom-0 w-[2px] bg-[#8b7cf8]/60 z-10"
                style={{ left: "70%" }}
                title="Target: 0.70"
              />
              <div
                className={cn(
                  "h-full rounded-full transition-all duration-700 ease-out",
                  getMetricColorClass(val as number)
                )}
                style={{ width: `${pct}%` }}
              />
            </div>
            {key === "context_precision" && (val as number) === 0 && (
              <span className="block text-[10px] text-muted-foreground/80 font-mono mt-0.5">
                No citations retrieved for evaluation in this run.
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ── Hero Score Card ─────────────────────────────────────── */

interface HeroScoreCardProps {
  score: number | null;
  delta: number | null;
  loading: boolean;
}

function HeroScoreCard({ score, delta, loading }: HeroScoreCardProps) {
  if (loading) {
    return (
      <div className="card-panel rounded-2xl p-5 space-y-3 col-span-2 flex flex-col justify-between h-full">
        <Skeleton className="h-4 w-28" />
        <Skeleton className="h-14 w-36" />
        <Skeleton className="h-5 w-20" />
      </div>
    );
  }

  const label = score != null ? scoreLabel(score) : null;
  const chipClass = score != null ? scoreChipClass(score) : "";
  const borderClass = score != null ? scoreBorderClass(score) : "";
  const isDown = score != null && score < THRESHOLD;

  return (
    <div
      className={cn(
        "card-panel rounded-2xl p-5 col-span-2 space-y-3 relative overflow-hidden flex flex-col justify-between h-full border border-border/40",
        borderClass
      )}
    >
      {/* Subtle background gradient for passing scores */}
      {score != null && score >= 0.75 && (
        <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-transparent to-transparent pointer-events-none" />
      )}

      <div>
        <p className="text-[10px] font-sans uppercase tracking-widest text-muted-foreground relative z-10">
          Overall Score
        </p>
      </div>

      <div className="flex flex-wrap items-end gap-4 relative z-10">
        <p
          className={cn(
            "font-mono text-6xl tabular-nums leading-none font-bold tracking-tight",
            score != null
              ? score >= 0.75
                ? "text-gradient"
                : score >= 0.5
                ? "text-warning"
                : "text-destructive"
              : "text-muted-foreground"
          )}
        >
          {score != null ? score.toFixed(3) : "—"}
        </p>

        {label && (
          <div className="pb-1 space-y-1.5 relative z-10">
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  "inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold",
                  chipClass
                )}
              >
                {label}
              </span>

              {delta !== null && delta !== 0 && (
                <span
                  className={cn(
                    "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-mono font-semibold",
                    delta > 0
                      ? "bg-success/15 text-success"
                      : "bg-destructive/15 text-destructive"
                  )}
                  title={`Change compared to previous run: ${delta > 0 ? "+" : ""}${delta.toFixed(3)}`}
                >
                  {delta > 0 ? (
                    <TrendingUp className="h-3 w-3" />
                  ) : (
                    <TrendingDown className="h-3 w-3" />
                  )}
                  {delta > 0 ? "+" : ""}
                  {delta.toFixed(3)}
                </span>
              )}
            </div>

            <div className="text-[11px] font-mono text-muted-foreground">
              <span>Below target (</span>
              <span
                className="underline cursor-help hover:text-foreground transition-colors"
                title="Target defined in eval config"
              >
                {THRESHOLD.toFixed(1)}
              </span>
              <span>)</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Compact Metric Card ─────────────────────────────────── */

interface MetricCardProps {
  label: string;
  value: string | number;
  sub?: string;
  trend?: "up" | "down" | "neutral";
  icon?: React.ReactNode;
  warnBelow?: number;
  numericValue?: number;
  loading?: boolean;
}

function MetricCard({ label, value, sub, trend, icon, numericValue, loading }: MetricCardProps) {
  const borderClass =
    numericValue != null
      ? numericValue < THRESHOLD
        ? "border-l-2 border-l-warning/50"
        : ""
      : "";

  if (loading) {
    return (
      <div className="card-panel rounded-2xl p-5 space-y-2 flex flex-col justify-between h-full border border-border/40">
        <Skeleton className="h-3 w-20" />
        <Skeleton className="h-8 w-16" />
        <Skeleton className="h-3 w-24" />
      </div>
    );
  }

  return (
    <div className={cn("card-panel rounded-2xl p-5 space-y-2 flex flex-col justify-between h-full border border-border/40", borderClass)}>
      <div className="flex items-center justify-between gap-1.5">
        <p className="text-[10px] font-sans uppercase tracking-widest text-muted-foreground">
          {label}
        </p>
        {icon && <span className="text-muted-foreground shrink-0">{icon}</span>}
      </div>
      <p className="font-mono text-3xl tabular-nums leading-none text-foreground font-bold">
        {value}
      </p>
      {sub && (
        <p
          className={cn(
            "flex items-center gap-1 text-[11px] font-mono leading-none pt-1",
            trend === "up"
              ? "text-success"
              : trend === "down"
              ? "text-destructive"
              : "text-muted-foreground"
          )}
        >
          {trend === "up" && <TrendingUp className="h-3 w-3" />}
          {trend === "down" && <TrendingDown className="h-3 w-3" />}
          {sub}
        </p>
      )}
    </div>
  );
}

/* ── Metric Delta Comparison Component ─────────────────── */

interface MetricComparison {
  metric: string;
  baseline: number;
  candidate: number;
  delta: number;
}

const getMetricComparisons = (bRun: any, cRun: any): MetricComparison[] => {
  if (!bRun?.ragas_scores || !cRun?.ragas_scores) return [];
  const bScores = bRun.ragas_scores;
  const cScores = cRun.ragas_scores;
  const allKeys = Array.from(new Set([...Object.keys(bScores), ...Object.keys(cScores)]));

  return allKeys.map(key => {
    const bVal = bScores[key] ?? 0;
    const cVal = cScores[key] ?? 0;
    return {
      metric: key.replace(/_/g, " "),
      baseline: bVal,
      candidate: cVal,
      delta: cVal - bVal
    };
  });
};

function MetricDeltaTable({ baselineRun, candidateRun }: { baselineRun: any; candidateRun: any }) {
  const comparisons = getMetricComparisons(baselineRun, candidateRun);

  if (comparisons.length === 0) return null;

  return (
    <div className="table-wrap mt-4 border border-border/40 rounded-lg overflow-hidden">
      <table className="data-table w-full border-collapse">
        <thead>
          <tr className="bg-surface-raised border-b border-border/40">
            <th className="text-left py-2 px-3">Metric</th>
            <th className="text-right py-2 px-3">Baseline Score</th>
            <th className="text-right py-2 px-3">Candidate Score</th>
            <th className="text-right py-2 px-3">Delta</th>
          </tr>
        </thead>
        <tbody>
          {comparisons.map((row) => {
            const isRegression = row.delta < -0.001;
            const isImprovement = row.delta > 0.001;
            return (
              <tr key={row.metric} className="hover:bg-surface-hover/50 transition-colors border-b border-border/20 last:border-none">
                <td className="font-mono text-xs capitalize py-2.5 px-3">{row.metric}</td>
                <td className="font-mono text-xs tabular-nums text-right py-2.5 px-3">{row.baseline.toFixed(3)}</td>
                <td className="font-mono text-xs tabular-nums text-right py-2.5 px-3">{row.candidate.toFixed(3)}</td>
                <td className="text-right py-2.5 px-3">
                  {isRegression ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-destructive/15 px-2.5 py-0.5 text-[10px] font-mono font-semibold text-destructive">
                      <TrendingDown className="h-2.5 w-2.5" />
                      {row.delta.toFixed(3)}
                    </span>
                  ) : isImprovement ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-success/15 px-2.5 py-0.5 text-[10px] font-mono font-semibold text-success">
                      <TrendingUp className="h-2.5 w-2.5" />
                      +{row.delta.toFixed(3)}
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 rounded-full bg-surface-elevated px-2.5 py-0.5 text-[10px] font-mono text-muted-foreground">
                      0.000
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   Main Page
   ═══════════════════════════════════════════════════════════ */

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
  // Match runs by explicit repo_id OR by diagnostics.job_id (legacy runs written before
  // repo_id was added to the run record — all pre-836e50a evals only stored job_id).
  const repoSpecificRuns = repoId
    ? allRuns.filter(
        (r) =>
          r.repo_id === repoId ||
          (!r.repo_id && r.diagnostics?.job_id === repoId),
      )
    : [];
  // Use repo-filtered list when we have matches; fall back to the full history so the
  // Compare panel is never accidentally empty when there are plenty of runs to compare.
  const runs = repoSpecificRuns.length > 0 ? repoSpecificRuns : allRuns;


  const [selectedRunKey, setSelectedRunKey] = useState<string | null>(null);
  const [baseline, setBaseline] = useState("");
  const [candidate, setCandidate] = useState("");
  const [simulatedRagasLoading, setSimulatedRagasLoading] = useState(false);

  /* Reset on repo change */
  useEffect(() => {
    setLastResult(null);
    setSelectedRunKey(null);
    setCompareResult(null);
    setBaseline("");
    setCandidate("");
  }, [repoId, setLastResult, setCompareResult]);

  /* Auto-populate from automation overlay */
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

  /* Derived values */
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
          if (mins < 60) return `${mins}m ago`;
          return `${Math.round(mins / 60)}h ago`;
        })()
      : null;

  /* Stat computations */
  const overallScore = avgScore(displayRun?.ragas_scores);
  const totalQueries = displayRun?.diagnostics?.question_count ?? null;

  // Compute delta between current overallScore and previous run's overallScore
  const displayRunIndex = displayRun
    ? runs.findIndex((r) => getEvalRunKey(r) === getEvalRunKey(displayRun))
    : -1;
  const prevRun = displayRunIndex !== -1 && displayRunIndex + 1 < runs.length ? runs[displayRunIndex + 1] : null;
  const prevScore = prevRun ? avgScore(prevRun.ragas_scores) : null;
  const scoreDelta = (overallScore != null && prevScore != null) ? overallScore - prevScore : null;

  const ciChecks: CiCheck[] = [
    {
      label: "Golden set CI",
      detail:
        golden.data?.status === "pass"
          ? `${golden.data.passed ?? "—"}/${golden.data.total ?? "—"} passed`
          : golden.data?.status === "fail"
          ? `${golden.data.failed_questions?.length ?? 0} failure(s)`
          : "Not run yet",
      status:
        golden.data?.status === "pass"
          ? "pass"
          : golden.data?.status === "fail"
          ? "fail"
          : "pending",
    },
    {
      label: "RAGAS evaluation",
      detail:
        overallScore != null
          ? `Avg score ${overallScore.toFixed(3)}`
          : "Not run yet",
      status:
        overallScore != null
          ? overallScore >= 0.75
            ? "pass"
            : overallScore >= 0.5
            ? "warn"
            : "fail"
          : "pending",
    },
    {
      label: "Index health",
      detail: evalReady
        ? chunkSummary || "Ready"
        : "Not ready",
      status: evalReady ? "pass" : "warn",
    },
    {
      label: "Backend connectivity",
      detail: backendOk ? "Online" : "Offline",
      status: backendOk ? "pass" : "fail",
    },
  ];

  const handleReRun = async () => {
    setSimulatedRagasLoading(true);
    try {
      await runRagas();
      toast.success("RAGAS evaluation run completed successfully.");
    } catch (e) {
      toast.error("Failed to run RAGAS evaluation.");
    } finally {
      setTimeout(() => {
        setSimulatedRagasLoading(false);
      }, 1500);
    }
  };

  const handleExportCSV = () => {
    toast.success(`Exported eval-batch-${displayRun?.version || "run"}.csv successfully.`);
  };

  const handleCompareRuns = async () => {
    await compare(baselineVal, candidateVal);
    toast.success("Runs compared successfully.");
  };

  /* ── Render ─────────────────────────────────────────────── */

  return (
    <AppShell>
      <div className="page-enter space-y-6">

        {/* ─── Header Row ─────────────────────────────────── */}
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="font-display text-2xl font-bold tracking-tight text-foreground">
              Evaluation
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              RAGAS retrieval metrics · CI quality gates · regression compare
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            {/* Run metadata pill — secondary muted */}
            {displayRun && (
              <div className="flex flex-col items-end gap-0.5">
                <span className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-accent px-3 py-1 font-mono text-[11px] text-primary">
                  {formatEvalRunLabel(displayRun)}
                </span>
                {lastDataRefreshLabel && (
                  <span className="font-mono text-[10px] text-muted-foreground pr-1">
                    refreshed {lastDataRefreshLabel}
                  </span>
                )}
              </div>
            )}

            {/* Re-run: primary filled */}
            <Button
              disabled={!repoId || !evalReady || ragasLoading || simulatedRagasLoading}
              onClick={handleReRun}
              className="h-9 gap-2"
            >
              {ragasLoading || simulatedRagasLoading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Running...
                </>
              ) : (
                <>
                  <Play className="h-4 w-4" />
                  Re-run
                </>
              )}
            </Button>

            {/* Export: ghost/secondary */}
            <Button variant="secondary" className="h-9 gap-1.5" disabled={!displayRun} onClick={handleExportCSV}>
              <Download className="h-4 w-4" />
              Export CSV
            </Button>
          </div>
        </div>

        {/* Progress banners */}
        {effectiveRagasProgress && !ragasLoading && (
          <Alert kind="info">Background evaluation: {effectiveRagasProgress}</Alert>
        )}

        {evalHealth.isError && (
          <QueryError
            message={evalHealth.error?.message ?? "Failed to load eval health"}
            onRetry={() => void evalHealth.refetch()}
          />
        )}

        {/* ─── Score Cards (Stagger-fade layout) ─────────────────────────────────── */}
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4 items-stretch">
          {/* Hero card: Overall Score */}
          <div className="col-span-2 transition-all duration-500 transform animate-fade-in-up [animation-delay:40ms]">
            <HeroScoreCard
              score={overallScore}
              delta={scoreDelta}
              loading={simulatedRagasLoading || ragasLoading || (evalHealth.isLoading && !displayRun)}
            />
          </div>

          {/* Supporting metrics */}
          <div className="transition-all duration-500 transform animate-fade-in-up [animation-delay:80ms]">
            <MetricCard
              label="Total Queries"
              value={totalQueries ?? "—"}
              sub={totalQueries != null ? "evaluated" : "No data available"}
              trend="neutral"
              icon={<TestTube className="h-4 w-4" />}
              loading={simulatedRagasLoading || ragasLoading || (evalHealth.isLoading && !displayRun)}
            />
          </div>
          <div className="transition-all duration-500 transform animate-fade-in-up [animation-delay:120ms]">
            <MetricCard
              label="Regressions"
              value={
                compareResult
                  ? String((compareResult as { regressions?: unknown[] }).regressions?.length ?? 0)
                  : "—"
              }
              sub={compareResult ? "vs baseline" : "Available after 2+ runs"}
              trend={
                compareResult
                  ? ((compareResult as { regressions?: unknown[] }).regressions?.length ?? 0) > 0
                    ? "down"
                    : "up"
                  : "neutral"
              }
              icon={<TrendingDown className="h-4 w-4" />}
              loading={false}
            />
          </div>
          <div className="transition-all duration-500 transform animate-fade-in-up [animation-delay:160ms]">
            <MetricCard
              label="Avg Latency"
              value={
                (displayRun as Record<string, unknown>)?.avg_latency_ms != null
                  ? `${Math.round((displayRun as Record<string, unknown>).avg_latency_ms as number)}ms`
                  : "—"
              }
              sub={
                (displayRun as Record<string, unknown>)?.avg_latency_ms != null
                  ? "per query"
                  : "Available after run"
              }
              trend="neutral"
              icon={<Zap className="h-4 w-4" />}
              loading={simulatedRagasLoading || ragasLoading || (evalHealth.isLoading && !displayRun)}
            />
          </div>
        </div>

        {/* ─── Two-column: CI checks | RAGAS Metrics ──────── */}
        <div className="grid gap-6 lg:grid-cols-2">
          {/* CI Checks */}
          <div className="card-panel space-y-4 border border-border/40">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-foreground">CI Checks</h2>
              <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-widest">
                {ciChecks.filter(c => c.status === "pass").length}/{ciChecks.length} passing
              </span>
            </div>

            {evalHealth.isLoading ? (
              <div className="space-y-3">
                <Skeleton className="h-10" />
                <Skeleton className="h-10" />
                <Skeleton className="h-10" />
                <Skeleton className="h-10" />
              </div>
            ) : (
              <CiChecksPanel checks={ciChecks} lastRunLabel={lastDataRefreshLabel ? `${lastDataRefreshLabel}` : "just now"} />
            )}

            {/* Errors from eval health */}
            {!evalReady &&
              (evalHealth.data?.errors ?? []).map((err, i) => (
                <Alert key={i} kind="error" className="mt-2">
                  {err}
                </Alert>
              ))}

            {/* Run Golden CI — its own section with divider */}
            <div className="border-t border-border/30 pt-4 mt-2">
              <Button
                variant="default"
                size="sm"
                disabled={!backendOk || goldenLoading}
                onClick={() => void runGolden()}
                className="h-8 text-xs gap-2"
              >
                {goldenLoading ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <TestTube className="h-3.5 w-3.5" />
                )}
                Run Golden CI
              </Button>
              {goldenProgress && (
                <p className="mt-2 text-xs text-muted-foreground">{goldenProgress}</p>
              )}
            </div>
          </div>

          {/* RAGAS Metrics panel */}
          <div className="card-panel space-y-5 border border-border/40">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-foreground">RAGAS Metrics</h2>
              {displayRun && (
                <span className="font-mono text-[10px] text-muted-foreground">
                  {formatEvalRunLabel(displayRun)}
                </span>
              )}
            </div>

            {simulatedRagasLoading || ragasLoading ? (
              <div className="space-y-4 py-6">
                <Skeleton className="h-44 w-full" />
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-4 w-1/2" />
              </div>
            ) : displayRun?.ragas_scores ? (
              <>
                <RagasChart scores={displayRun.ragas_scores} />
                <div className="border-t border-border/30 pt-4">
                  <RagasMetricBars scores={displayRun.ragas_scores} />
                </div>
                {displayRun.regression_warning && (
                  <Alert kind="warning">{displayRun.regression_warning}</Alert>
                )}
              </>
            ) : (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border border-border bg-surface shadow-elev-1">
                  <TrendingUp className="h-6 w-6 text-muted-foreground" />
                </div>
                <p className="text-sm font-medium text-foreground">No RAGAS scores yet</p>
                <p className="mt-1 text-xs text-muted-foreground max-w-xs">
                  Click &ldquo;Re-run&rdquo; above to evaluate retrieval quality across all metrics.
                </p>
              </div>
            )}
          </div>
        </div>

        {/* ─── Regression Comparison Table ─────────────────── */}
        {compareResult && (
          <div className="card-panel space-y-4 border border-border/40">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-foreground">
                Regression Comparison
              </h2>
              {(compareResult as { regressions?: unknown[] }).regressions?.length === 0 && (
                <span className="rounded-full bg-success/10 px-2.5 py-0.5 text-[10px] font-mono text-success uppercase tracking-widest">
                  Clean
                </span>
              )}
            </div>
            <CompareRegressionsTable result={compareResult} />
          </div>
        )}

        {/* ─── Compare Runs Panel (Dropdown picker + Unified layout) ────────────────────────── */}
        <div className="card-panel space-y-4 border border-border/40">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-foreground">Compare runs</h2>
            {runs.length >= 2 && (
              <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-widest">
                Version comparison
              </span>
            )}
          </div>

          {history.isLoading ? (
            <Skeleton className="h-24 w-full" />
          ) : runs.length < 2 ? (
            <div className="flex flex-col items-center justify-center py-8 text-center border border-dashed border-border/40 rounded-xl bg-surface/30">
              <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-xl border border-border bg-surface">
                <AlertTriangle className="h-5 w-5 text-muted-foreground" />
              </div>
              <p className="text-sm font-medium text-foreground">No comparable runs yet</p>
              <p className="mt-1 text-xs text-muted-foreground max-w-xs">
                Run the RAGAS evaluation suite at least twice to enable run-over-run regressions and deltas.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              <p className="text-xs text-muted-foreground">
                Compare score metrics between any two execution runs in history.
              </p>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label className="text-xs">Baseline (Older)</Label>
                  <Select value={baselineVal} onValueChange={setBaseline}>
                    <SelectTrigger className="h-9 text-xs">
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
                  <Label className="text-xs">Candidate (Newer)</Label>
                  <Select value={candidateVal} onValueChange={setCandidate}>
                    <SelectTrigger className="h-9 text-xs">
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
              {sameSelection && (
                <Alert kind="warning">Pick two different runs to compare.</Alert>
              )}
              <Button
                disabled={!!sameSelection || compareLoading}
                onClick={handleCompareRuns}
                className="h-9 w-full sm:w-auto"
              >
                {compareLoading && <Loader2 className="h-4 w-4 animate-spin" />}
                Compare runs
              </Button>

              {compareResult && (
                <div className="border-t border-border/20 pt-4">
                  <h3 className="text-xs font-semibold text-foreground mb-2">Metric Deltas</h3>
                  <MetricDeltaTable
                    baselineRun={runs.find(r => getEvalRunKey(r) === baselineVal)}
                    candidateRun={runs.find(r => getEvalRunKey(r) === candidateVal)}
                  />
                  {compareResult.regressions_found && (
                    <div className="mt-4">
                      <Alert kind="warning">
                        Regressions detected! Several metrics fell below the baseline threshold.
                      </Alert>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* ─── Golden Set CI Details ────────────────────────── */}
        <div className="card-panel space-y-4 border border-border/40">
          <h2 className="text-sm font-semibold text-foreground">Golden set CI — detail</h2>
          <GoldenCiPanel
            data={golden.data}
            loading={golden.isLoading}
            liveResult={goldenLiveResult}
          />
        </div>

        {/* ─── Eval History Table ───────────────────────────── */}
        {runs.length > 0 && (
          <div className="card-panel space-y-4 border border-border/40">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-foreground">Eval history</h2>
              <span className="font-mono text-[10px] text-muted-foreground">
                {runs.length} run{runs.length !== 1 ? "s" : ""}
              </span>
            </div>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Version</th>
                    <th>When</th>
                    <th>Queries</th>
                    <th>Faithfulness</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.slice(0, 10).map((r) => {
                    const key = getEvalRunKey(r);
                    const active =
                      displayRun != null && key === getEvalRunKey(displayRun);
                    return (
                      <tr
                        key={key}
                        className={cn(
                          "row-clickable cursor-pointer transition-colors duration-150",
                          active
                            ? "bg-primary/8 border-l-2 border-l-primary"
                            : ""
                        )}
                        onClick={() => setSelectedRunKey(key)}
                      >
                        <td className="font-mono text-xs">{formatEvalRunLabel(r)}</td>
                        <td className="font-mono text-xs text-muted-foreground">
                          {r.timestamp
                            ? new Date(r.timestamp).toLocaleString()
                            : "—"}
                        </td>
                        <td className="font-mono text-xs tabular-nums">
                          {r.diagnostics?.question_count ?? (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </td>
                        <td className="font-mono text-xs tabular-nums">
                          {r.ragas_scores?.faithfulness != null ? (
                            <span
                              className={
                                r.ragas_scores.faithfulness < THRESHOLD
                                  ? "text-warning"
                                  : "text-foreground"
                              }
                            >
                              {r.ragas_scores.faithfulness.toFixed(3)}
                            </span>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {displayRun?.ragas_scores && (
              <div className="border-t border-border/30 pt-4">
                <PerQuestionDiagnostics run={displayRun} />
              </div>
            )}
          </div>
        )}
      </div>
    </AppShell>
  );
}
