"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Loader2, Play, TestTube } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  compareEvalRuns,
  getEvalJobStatus,
  startEval,
  startGoldenRun,
} from "@/lib/api";
import { useApp } from "@/lib/context/app-context";
import { useBackendOnline } from "@/lib/hooks/use-backend-health";
import { useEvalHealth } from "@/lib/hooks/use-eval-health";
import { useEvalHistory } from "@/lib/hooks/use-eval-history";
import { useRepoStatus } from "@/lib/hooks/use-repo-status";
import { ApiError, type EvalRun } from "@/lib/types";
import { AppShell } from "@/components/layout/app-shell";
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
import { useGoldenStatus } from "@/lib/hooks/use-golden-status";

async function pollEvalJob(
  jobId: string,
  onTick?: (status: string) => void,
  maxMs = 1_800_000,
): Promise<Awaited<ReturnType<typeof getEvalJobStatus>>> {
  const t0 = Date.now();
  while (Date.now() - t0 < maxMs) {
    const st = await getEvalJobStatus(jobId);
    onTick?.(st.status);
    if (st.status === "done" || st.status === "error") return st;
    await new Promise((r) => setTimeout(r, 3000));
  }
  throw new Error("Timed out after 30 minutes");
}

export default function EvaluationPage() {
  const { repoId } = useApp();
  const qc = useQueryClient();
  const { online: backendOk } = useBackendOnline();
  const status = useRepoStatus(repoId);
  const evalHealth = useEvalHealth(repoId, status.data);
  const history = useEvalHistory(backendOk);
  const golden = useGoldenStatus(backendOk);

  const [ragasLoading, setRagasLoading] = useState(false);
  const [goldenLoading, setGoldenLoading] = useState(false);
  const [lastResult, setLastResult] = useState<EvalRun | null>(null);
  const [compareLoading, setCompareLoading] = useState(false);
  const [compareResult, setCompareResult] = useState<Awaited<
    ReturnType<typeof compareEvalRuns>
  > | null>(null);

  const runs = history.data ?? [];
  const [baseline, setBaseline] = useState("");
  const [candidate, setCandidate] = useState("");

  const baselineVal = baseline || runs[0]?.version || "";
  const candidateVal =
    candidate || (runs.length > 1 ? runs[1]?.version : runs[0]?.version) || "";
  const sameSelection = baselineVal && candidateVal && baselineVal === candidateVal;

  const evalReady = Boolean(evalHealth.data?.ok);
  const details = evalHealth.data?.details ?? {};

  async function runRagas() {
    if (!repoId) return;
    setRagasLoading(true);
    setLastResult(null);
    try {
      const { job_id } = await startEval(repoId);
      toast.info("RAGAS evaluation queued");
      void qc.invalidateQueries({ queryKey: ["evalHealth", repoId] });
      const done = await pollEvalJob(job_id);
      if (done.status === "error") {
        toast.error(done.error ?? "Eval failed");
      } else if (done.result && "ragas_scores" in done.result) {
        setLastResult(done.result as EvalRun);
        toast.success("Evaluation complete");
        void qc.invalidateQueries({ queryKey: ["evalHistory"] });
      }
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Eval failed");
    } finally {
      setRagasLoading(false);
    }
  }

  async function runGolden() {
    setGoldenLoading(true);
    try {
      const { job_id } = await startGoldenRun();
      toast.info("Golden CI running…");
      const t0 = Date.now();
      while (Date.now() - t0 < 1_200_000) {
        const st = await getEvalJobStatus(job_id);
        if (st.status === "done") {
          toast.success("Golden CI complete");
          void golden.refetch();
          break;
        }
        if (st.status === "error") {
          toast.error(st.error ?? "Golden CI failed");
          break;
        }
        await new Promise((r) => setTimeout(r, 2000));
      }
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Golden CI failed");
    } finally {
      setGoldenLoading(false);
    }
  }

  async function compare() {
    if (sameSelection) return;
    setCompareLoading(true);
    setCompareResult(null);
    try {
      const res = await compareEvalRuns(baselineVal, candidateVal);
      setCompareResult(res);
      if (res.regressions_found) toast.warning("Regressions detected");
      else toast.success("No regressions within tolerance");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Compare failed");
    } finally {
      setCompareLoading(false);
    }
  }

  return (
    <AppShell>
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25 }}
        className="space-y-8"
      >
        <SectionHeader
          title="Evaluation & quality assurance"
          caption="RAGAS metrics, version compare, golden-set CI"
        />

        {!repoId ? (
          <EmptyState
            title="No repository selected"
            description="Ingest a repo on the Workspace tab first."
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
              />
              <StatCard
                label="Chunks"
                value={String(details.chroma_chunk_count ?? "—")}
              />
              <StatCard
                label="Probe hits"
                value={String(details.probe_hit_count ?? "—")}
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

        <div className="flex flex-wrap gap-3">
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
        </div>

        {lastResult?.ragas_scores && (
          <div className="rounded-xl border border-border bg-surface p-5">
            <SectionHeader title="RAGAS scores" />
            <RagasChart scores={lastResult.ragas_scores} />
            {lastResult.regression_warning && (
              <Alert kind="warning" className="mt-4">
                {lastResult.regression_warning}
              </Alert>
            )}
            <PerQuestionDiagnostics run={lastResult} />
          </div>
        )}

        <div className="rounded-xl border border-border bg-surface p-5">
          <SectionHeader title="Compare versions" />
          {runs.length < 2 ? (
            <p className="text-sm text-muted-foreground">
              Run RAGAS eval at least twice to compare versions.
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
                      {runs.map((r) => (
                        <SelectItem key={r.version} value={r.version}>
                          {r.version}
                        </SelectItem>
                      ))}
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
                      {runs.map((r) => (
                        <SelectItem key={r.version} value={r.version}>
                          {r.version}
                        </SelectItem>
                      ))}
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
                onClick={() => void compare()}
              >
                {compareLoading && <Loader2 className="h-4 w-4 animate-spin" />}
                Compare runs
              </Button>
              {compareResult && (
                <p className="mt-3 text-sm">
                  {compareResult.regressions_found
                    ? `${compareResult.regressions.length} regression(s) found`
                    : "No regressions within tolerance"}
                </p>
              )}
            </>
          )}
        </div>

        <div className="rounded-xl border border-border bg-surface p-5">
          <SectionHeader title="Golden set CI" />
          {golden.isLoading ? (
            <Skeleton className="h-16 w-full" />
          ) : (
            <div className="grid gap-3 sm:grid-cols-3">
              <StatCard
                label="Status"
                value={(golden.data?.status ?? "not_yet_run").toUpperCase()}
              />
              <StatCard
                label="Score"
                value={
                  golden.data?.score != null
                    ? `${Math.round(golden.data.score * 100)}%`
                    : "—"
                }
              />
              <StatCard
                label="Passed"
                value={`${golden.data?.passed ?? "—"}/${golden.data?.total ?? "—"}`}
              />
            </div>
          )}
        </div>
      </motion.div>
    </AppShell>
  );
}
