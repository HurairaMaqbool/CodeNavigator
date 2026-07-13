"use client";

/**
 * Automatic eval triggers (RAGAS after index/commit/query threshold, compare after new runs).
 *
 * ROLLBACK: Remove this component from providers.tsx and delete automation files —
 * manual buttons in useEvalRunners stay unchanged.
 */
import { useCallback, useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { ChatQuerySuccessDetail } from "@/lib/chat-query-events";
import { getEvalHealth } from "@/lib/api";
import { repoIsReady } from "@/lib/constants";
import { useApp } from "@/lib/context/app-context";
import { refreshEvalCachesQuietly } from "@/lib/eval-data-refresh";
import {
  CHAT_QUERY_SUCCESS_EVENT,
  incrementChatQueryCount,
  logEvalAutomation,
  readLastAutoIndexCommit,
  scheduleIndexDebounced,
  scheduleQueryRagasDebounced,
  scheduleQueryRefreshDebounced,
  shouldTriggerQueryRagas,
  writeLastAutoIndexCommit,
} from "@/lib/eval-automation-state";
import {
  autoCompareLatestRuns,
  runRagasEval,
} from "@/lib/eval-runners";
import { useEvalHistory } from "@/lib/hooks/use-eval-history";
import { useRepoStatus } from "@/lib/hooks/use-repo-status";

export function EvalAutomationBridge() {
  const { repoId } = useApp();
  const qc = useQueryClient();
  const status = useRepoStatus(repoId);
  const history = useEvalHistory(Boolean(repoId));
  const prevReadyRef = useRef(false);
  const prevCommitRef = useRef<string | null>(null);
  const prevRunCountRef = useRef(0);
  const pipelineInFlightRef = useRef(false);

  const ready = Boolean(status.data && repoIsReady(status.data));
  const commitHash = status.data?.commit_hash ?? null;

  useEffect(() => {
    prevReadyRef.current = false;
    prevCommitRef.current = null;
    prevRunCountRef.current = 0;
    pipelineInFlightRef.current = false;
  }, [repoId]);

  const runAutoEvalPipeline = useCallback(
    async (reason: string, commit: string | null) => {
      if (!repoId) return;
      if (pipelineInFlightRef.current) {
        logEvalAutomation("pipeline_skipped_inflight", { repoId, reason });
        return;
      }
      pipelineInFlightRef.current = true;

      try {
        if (commit) writeLastAutoIndexCommit(repoId, commit);
        refreshEvalCachesQuietly(repoId, qc, `${reason}_preflight`);

        const health = await getEvalHealth(repoId, false);
        if (!health.ok) {
          logEvalAutomation("ragas_skipped_not_ready", {
            repoId,
            reason,
            errors: health.errors,
          });
          return;
        }

        qc.setQueryData(["evalAutoProgress", repoId], "Running RAGAS…");
        const run = await runRagasEval({
          repoId,
          qc,
          silent: true,
          onProgress: (msg) => {
            if (msg) qc.setQueryData(["evalAutoProgress", repoId], msg);
          },
        });
        qc.setQueryData(["evalAutoProgress", repoId], null);

        if (run) {
          qc.setQueryData(["evalAutoLastRun", repoId], run);
          await autoCompareLatestRuns(repoId, qc);
        }
        refreshEvalCachesQuietly(repoId, qc, `${reason}_post_ragas`);
      } catch (err) {
        logEvalAutomation("pipeline_error", {
          repoId,
          reason,
          error: err instanceof Error ? err.message : String(err),
        });
        if (process.env.NODE_ENV === "development") {
          console.error("[eval-automation] pipeline failed", err);
        }
      } finally {
        pipelineInFlightRef.current = false;
        qc.setQueryData(["evalAutoProgress", repoId], null);
      }
    },
    [repoId, qc],
  );

  // Trigger 1: Index ready / new commit — debounced RAGAS + golden refresh
  useEffect(() => {
    if (!repoId || !ready || !commitHash) {
      prevReadyRef.current = ready;
      return;
    }

    const becameReady = !prevReadyRef.current && ready;
    const commitChanged =
      prevCommitRef.current != null && prevCommitRef.current !== commitHash;
    const alreadyHandled = readLastAutoIndexCommit(repoId) === commitHash;

    prevReadyRef.current = ready;
    prevCommitRef.current = commitHash;

    if (!becameReady && !commitChanged) return;
    if (alreadyHandled && !commitChanged) return;

    logEvalAutomation("index_event_scheduled", {
      repoId,
      commitHash,
      becameReady,
      commitChanged,
    });

    scheduleIndexDebounced(repoId, () => {
      void runAutoEvalPipeline("index", commitHash);
    });
  }, [repoId, ready, commitHash, runAutoEvalPipeline]);

  // Trigger 2: New eval run in history — auto-compare latest pair
  useEffect(() => {
    if (!repoId) return;
    const count = history.data?.length ?? 0;
    const prev = prevRunCountRef.current;
    if (count >= 2 && count > prev && prev > 0) {
      void (async () => {
        try {
          await autoCompareLatestRuns(repoId, qc);
        } catch (err) {
          logEvalAutomation("history_compare_error", {
            repoId,
            error: err instanceof Error ? err.message : String(err),
          });
        }
      })();
    }
    prevRunCountRef.current = count;
  }, [repoId, history.data?.length, qc]);

  // Trigger 3: Successful chat query — debounced cache refresh + RAGAS every N queries
  useEffect(() => {
    if (!repoId) return;

    const onChatQuerySuccess = (event: Event) => {
      const detail = (event as CustomEvent<ChatQuerySuccessDetail>).detail;
      if (!detail?.repoId || detail.repoId !== repoId) return;

      scheduleQueryRefreshDebounced(repoId, () => {
        refreshEvalCachesQuietly(repoId, qc, "chat_query");
      });

      const queryCount = incrementChatQueryCount(repoId);
      logEvalAutomation("chat_query_recorded", { repoId, queryCount });

      if (!ready) return;

      if (shouldTriggerQueryRagas(queryCount)) {
        logEvalAutomation("query_ragas_threshold_scheduled", {
          repoId,
          queryCount,
        });
        scheduleQueryRagasDebounced(repoId, () => {
          void runAutoEvalPipeline("query_threshold", commitHash);
        });
      }
    };

    window.addEventListener(CHAT_QUERY_SUCCESS_EVENT, onChatQuerySuccess);
    return () => {
      window.removeEventListener(CHAT_QUERY_SUCCESS_EVENT, onChatQuerySuccess);
    };
  }, [repoId, ready, commitHash, qc, runAutoEvalPipeline]);

  return null;
}

function useEvalAutomationQuery<T>(
  key: string,
  repoId: string | null,
  initialData: T,
) {
  return useQuery<T>({
    queryKey: [key, repoId],
    queryFn: () => initialData,
    enabled: Boolean(repoId),
    initialData,
    staleTime: Infinity,
  });
}

/** Read automation progress / compare for Evaluation page (optional overlay). */
export function useEvalAutomationOverlay(repoId: string | null) {
  const autoProgress = useEvalAutomationQuery<string | null>(
    "evalAutoProgress",
    repoId,
    null,
  );
  const autoCompare = useEvalAutomationQuery(
    "evalAutoCompare",
    repoId,
    null,
  );
  const autoLastRun = useEvalAutomationQuery(
    "evalAutoLastRun",
    repoId,
    null,
  );
  const autoLastRefresh = useEvalAutomationQuery<number | null>(
    "evalAutoLastRefresh",
    repoId,
    null,
  );

  return {
    autoProgress: autoProgress.data,
    autoCompareResult: autoCompare.data,
    autoLastRun: autoLastRun.data,
    autoLastRefreshAt: autoLastRefresh.data,
  };
}
