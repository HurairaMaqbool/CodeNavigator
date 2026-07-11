"use client";

import { useQuery } from "@tanstack/react-query";
import { getIngestStatus } from "@/lib/api";
import type { IngestStatusResponse } from "@/lib/types";

export function useRepoStatus(repoId: string | null) {
  return useQuery<IngestStatusResponse>({
    queryKey: ["status", repoId],
    queryFn: () => getIngestStatus(repoId!),
    enabled: Boolean(repoId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (!status || status === "ready" || status === "failed") return false;
      return 2000;
    },
    staleTime: 1000,
  });
}
