"use client";

import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getEvalHealth } from "@/lib/api";
import { repoIsReady } from "@/lib/constants";
import type { IngestStatusResponse } from "@/lib/types";

export function useEvalHealth(
  repoId: string | null,
  statusData?: IngestStatusResponse,
) {
  const qc = useQueryClient();
  const statusReady = Boolean(statusData && repoIsReady(statusData));

  useEffect(() => {
    if (!repoId || !statusReady) return;
    void qc.invalidateQueries({ queryKey: ["evalHealth", repoId] });
  }, [repoId, statusReady, qc]);

  return useQuery({
    queryKey: ["evalHealth", repoId],
    queryFn: () => getEvalHealth(repoId!, false),
    enabled: Boolean(repoId),
    staleTime: 60_000,
    refetchOnMount: (query) => {
      if (statusReady && !query.state.data?.ok) {
        return "always";
      }
      return true;
    },
  });
}
