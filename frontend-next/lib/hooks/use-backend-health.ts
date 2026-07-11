"use client";

import { useQuery } from "@tanstack/react-query";
import { checkHealth } from "@/lib/api";

export function useBackendHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: checkHealth,
    refetchInterval: 30_000,
    retry: 1,
    staleTime: 25_000,
  });
}

/** True only after a successful health probe — false while loading or on error. */
export function useBackendOnline() {
  const q = useBackendHealth();
  const online = q.isSuccess && q.data?.status === "ok";
  const offline = q.isError || (q.isSuccess && q.data?.status !== "ok");
  return { ...q, online, offline };
}
