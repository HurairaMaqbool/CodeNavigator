/**
 * Cross-screen query invalidation — single place for repo-scoped cache coherence.
 * Chat, Evaluation, Connect, and Platform must call these after repo-changing actions.
 */
import type { QueryClient } from "@tanstack/react-query";

/** Invalidate all caches tied to a repository job id. */
export function invalidateRepoQueries(
  qc: QueryClient,
  repoId: string | null | undefined,
) {
  if (repoId) {
    void qc.invalidateQueries({ queryKey: ["status", repoId] });
    void qc.invalidateQueries({ queryKey: ["evalHealth", repoId] });
  }
}

/** After ingest, re-index, or purge — refresh every screen that shows index state. */
export function invalidateAfterRepoMutation(
  qc: QueryClient,
  repoId: string | null | undefined,
) {
  invalidateRepoQueries(qc, repoId);
  void qc.invalidateQueries({ queryKey: ["platformRepos"] });
  void qc.invalidateQueries({ queryKey: ["evalHistory"] });
  void qc.invalidateQueries({ queryKey: ["goldenStatus"] });
}
