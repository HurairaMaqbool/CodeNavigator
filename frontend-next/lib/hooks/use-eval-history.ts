"use client";

import { useQuery } from "@tanstack/react-query";
import { getEvalHistory } from "@/lib/api";
import { normalizeEvalHistory } from "@/lib/eval-run-utils";
import { getEvalRunKey } from "@/lib/utils";
import type { EvalRun } from "@/lib/types";

function assertUniqueRunIds(runs: EvalRun[]): EvalRun[] {
  const keys = runs.map(getEvalRunKey);
  const dupes = keys.filter((key, index) => keys.indexOf(key) !== index);
  if (dupes.length > 0) {
    console.warn(
      "[evalHistory] Duplicate run_id(s) from API — dropdown keys may collide:",
      [...new Set(dupes)],
    );
  }
  return runs;
}

export function useEvalHistory(enabled = true) {
  return useQuery({
    queryKey: ["evalHistory"],
    queryFn: async () => assertUniqueRunIds(normalizeEvalHistory(await getEvalHistory())),
    enabled,
    staleTime: 120_000,
  });
}
