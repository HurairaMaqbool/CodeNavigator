/**
 * Shared eval runners — used by Evaluation page (manual) and EvalAutomationBridge (auto).
 * Internal logic unchanged from original page handlers; only extracted + silent mode.
 */
import type { QueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  compareEvalRuns,
  getEvalHistory,
  startEval,
  startGoldenRun,
} from "@/lib/api";
import {
  formatEvalJobError,
  pollEvalJob,
} from "@/lib/eval-job-poll";
import { normalizeEvalRun, normalizeEvalHistory } from "@/lib/eval-run-utils";
import { invalidateAfterRepoMutation } from "@/lib/repo-sync";
import { getEvalRunKey } from "@/lib/utils";
import { ApiError, type CompareResult, type EvalRun, type GoldenStatus } from "@/lib/types";
import {
  logEvalAutomation,
  readLastAutoComparePair,
  releaseEvalLock,
  tryAcquireEvalLock,
  writeLastAutoComparePair,
} from "@/lib/eval-automation-state";

export type RunRagasOptions = {
  repoId: string;
  qc: QueryClient;
  silent?: boolean;
  onProgress?: (msg: string | null) => void;
};

export type RunGoldenOptions = {
  qc: QueryClient;
  silent?: boolean;
  onProgress?: (msg: string | null) => void;
};

export type CompareRunsOptions = {
  repoId: string;
  baselineKey: string;
  candidateKey: string;
  qc: QueryClient;
  silent?: boolean;
  skipIfSamePair?: boolean;
};

export async function runRagasEval(
  opts: RunRagasOptions,
): Promise<EvalRun | null> {
  const { repoId, qc, silent, onProgress } = opts;
  if (!tryAcquireEvalLock(repoId, "ragas")) {
    logEvalAutomation("ragas_skipped_locked", { repoId });
    return null;
  }
  onProgress?.("Starting…");
  try {
    const { job_id } = await startEval(repoId);
    if (!silent) {
      toast.info("RAGAS evaluation queued", { id: "ragas-start" });
    }
    void qc.invalidateQueries({ queryKey: ["evalHealth", repoId] });
    invalidateAfterRepoMutation(qc, repoId);
    const done = await pollEvalJob(job_id, {
      silent,
      onStatus: (st) =>
        onProgress?.(st === "running" ? "Running…" : st),
    });
    if (done.status === "error") {
      if (!silent) toast.error(formatEvalJobError(done));
      logEvalAutomation("ragas_error", { repoId, error: formatEvalJobError(done) });
      return null;
    }
    if (done.status === "done" && done.result && "ragas_scores" in done.result) {
      const normalized = normalizeEvalRun(done.result as EvalRun);
      if (!silent) toast.success("Evaluation complete");
      void qc.invalidateQueries({ queryKey: ["evalHistory"] });
      return normalized;
    }
    if (!silent) toast.error(formatEvalJobError(done));
    return null;
  } catch (e) {
    const msg =
      e instanceof ApiError
        ? e.message
        : e instanceof Error
          ? e.message
          : "Eval failed";
    if (!silent) toast.error(msg);
    logEvalAutomation("ragas_exception", { repoId, error: msg });
    return null;
  } finally {
    releaseEvalLock(repoId, "ragas");
    onProgress?.(null);
  }
}

export async function runGoldenCi(
  opts: RunGoldenOptions,
): Promise<GoldenStatus | null> {
  const { qc, silent, onProgress } = opts;
  const lockKey = "__global__";
  if (!tryAcquireEvalLock(lockKey, "golden")) {
    logEvalAutomation("golden_skipped_locked", {});
    return null;
  }
  onProgress?.("Starting…");
  try {
    const { job_id } = await startGoldenRun();
    if (!silent) {
      toast.info("Golden CI running…", { id: "golden-start" });
    }
    const done = await pollEvalJob(job_id, {
      silent,
      onStatus: (st) =>
        onProgress?.(st === "running" ? "Running…" : st),
    });
    if (done.status === "error") {
      if (!silent) toast.error(formatEvalJobError(done));
      logEvalAutomation("golden_error", { error: formatEvalJobError(done) });
      return null;
    }
    if (done.status === "done") {
      const result = done.result as GoldenStatus | undefined;
      if (!silent && result?.status) {
        toast.success(
          result.status === "pass"
            ? "Golden CI passed"
            : `Golden CI finished (${result.passed}/${result.total} passed)`,
        );
      }
      void qc.invalidateQueries({ queryKey: ["goldenStatus"] });
      return result ?? null;
    }
    return null;
  } catch (e) {
    const msg =
      e instanceof ApiError
        ? e.message
        : e instanceof Error
          ? e.message
          : "Golden CI failed";
    if (!silent) toast.error(msg);
    logEvalAutomation("golden_exception", { error: msg });
    return null;
  } finally {
    releaseEvalLock(lockKey, "golden");
    onProgress?.(null);
  }
}

export async function compareEvalRunsSafe(
  opts: CompareRunsOptions,
): Promise<CompareResult | null> {
  const { repoId, baselineKey, candidateKey, qc, silent, skipIfSamePair } =
    opts;
  if (!baselineKey || !candidateKey || baselineKey === candidateKey) {
    return null;
  }
  const pairKey = `${baselineKey}|${candidateKey}`;
  if (skipIfSamePair && readLastAutoComparePair(repoId) === pairKey) {
    logEvalAutomation("compare_skipped_same_pair", { repoId, pairKey });
    return null;
  }
  if (!tryAcquireEvalLock(repoId, "compare")) {
    logEvalAutomation("compare_skipped_locked", { repoId });
    return null;
  }
  try {
    const res = await compareEvalRuns(baselineKey, candidateKey);
    writeLastAutoComparePair(repoId, pairKey);
    qc.setQueryData(["evalAutoCompare", repoId], res);
    if (!silent) {
      if (res.incomparable) {
        toast.warning(
          res.incomparable_reason ?? "Runs cannot be compared",
          { id: "eval-compare-result" },
        );
      } else if (res.regressions_found) {
        toast.warning(
          `${res.regressions.length} regression(s) detected`,
          { id: "eval-compare-result" },
        );
      } else {
        toast.success("No regressions within tolerance", {
          id: "eval-compare-result",
        });
      }
    }
    return res;
  } catch (e) {
    const msg = e instanceof ApiError ? e.message : "Compare failed";
    if (!silent) toast.error(msg);
    logEvalAutomation("compare_exception", { repoId, error: msg });
    return null;
  } finally {
    releaseEvalLock(repoId, "compare");
  }
}

/** After RAGAS completes, compare the two newest runs if available. */
export async function autoCompareLatestRuns(
  repoId: string,
  qc: QueryClient,
): Promise<CompareResult | null> {
  try {
    const runs = normalizeEvalHistory(await getEvalHistory());
    if (runs.length < 2) return null;
    const baselineKey = getEvalRunKey(runs[0]);
    const candidateKey = getEvalRunKey(runs[1]);
    return compareEvalRunsSafe({
      repoId,
      baselineKey,
      candidateKey,
      qc,
      silent: true,
      skipIfSamePair: true,
    });
  } catch (e) {
    logEvalAutomation("auto_compare_fetch_failed", {
      repoId,
      error: e instanceof Error ? e.message : String(e),
    });
    return null;
  }
}
