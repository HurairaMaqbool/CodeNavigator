import type { QueryClient } from "@tanstack/react-query";
import { logEvalAutomation } from "@/lib/eval-automation-state";

/** Lightweight cache refresh — does not start RAGAS/Golden jobs. */
export function refreshEvalCachesQuietly(
  repoId: string,
  qc: QueryClient,
  reason: string,
): void {
  try {
    void qc.invalidateQueries({ queryKey: ["evalHealth", repoId] });
    void qc.invalidateQueries({ queryKey: ["evalHistory"] });
    void qc.invalidateQueries({ queryKey: ["goldenStatus"] });
    void qc.refetchQueries({ queryKey: ["evalHealth", repoId] });
    void qc.refetchQueries({ queryKey: ["evalHistory"] });
    void qc.refetchQueries({ queryKey: ["goldenStatus"] });
    qc.setQueryData(["evalAutoLastRefresh", repoId], Date.now());
    logEvalAutomation("eval_cache_refresh", { repoId, reason });
  } catch (err) {
    logEvalAutomation("eval_cache_refresh_error", {
      repoId,
      reason,
      error: err instanceof Error ? err.message : String(err),
    });
  }
}
