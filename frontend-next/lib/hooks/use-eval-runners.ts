"use client";

import { useCallback, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { CompareResult, EvalRun, GoldenStatus } from "@/lib/types";
import {
  autoCompareLatestRuns,
  compareEvalRunsSafe,
  runGoldenCi,
  runRagasEval,
} from "@/lib/eval-runners";

/** Manual eval controls — same behavior as original Evaluation page buttons. */
export function useEvalRunners(repoId: string | null) {
  const qc = useQueryClient();
  const [ragasLoading, setRagasLoading] = useState(false);
  const [goldenLoading, setGoldenLoading] = useState(false);
  const [compareLoading, setCompareLoading] = useState(false);
  const [ragasProgress, setRagasProgress] = useState<string | null>(null);
  const [goldenProgress, setGoldenProgress] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<EvalRun | null>(null);
  const [goldenLiveResult, setGoldenLiveResult] = useState<GoldenStatus | null>(
    null,
  );
  const [compareResult, setCompareResult] = useState<CompareResult | null>(null);
  const compareToastShown = useRef(false);

  const runRagas = useCallback(async () => {
    if (!repoId) return;
    setRagasLoading(true);
    setLastResult(null);
    try {
      const result = await runRagasEval({
        repoId,
        qc,
        silent: false,
        onProgress: setRagasProgress,
      });
      if (result) setLastResult(result);
    } finally {
      setRagasLoading(false);
    }
  }, [repoId, qc]);

  const runGolden = useCallback(async () => {
    setGoldenLoading(true);
    setGoldenLiveResult(null);
    try {
      const result = await runGoldenCi({
        qc,
        silent: false,
        onProgress: setGoldenProgress,
      });
      if (result) setGoldenLiveResult(result);
    } finally {
      setGoldenLoading(false);
    }
  }, [qc]);

  const compare = useCallback(
    async (baselineKey: string, candidateKey: string) => {
      if (!repoId || baselineKey === candidateKey) return;
      setCompareLoading(true);
      setCompareResult(null);
      compareToastShown.current = false;
      try {
        const res = await compareEvalRunsSafe({
          repoId,
          baselineKey,
          candidateKey,
          qc,
          silent: false,
        });
        if (res) setCompareResult(res);
      } finally {
        setCompareLoading(false);
      }
    },
    [repoId, qc],
  );

  const autoCompare = useCallback(async () => {
    if (!repoId) return null;
    return autoCompareLatestRuns(repoId, qc);
  }, [repoId, qc]);

  return {
    runRagas,
    runGolden,
    compare,
    autoCompare,
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
  };
}
