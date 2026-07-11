"use client";

import { useQuery } from "@tanstack/react-query";
import { getEvalHistory } from "@/lib/api";

export function useEvalHistory(enabled = true) {
  return useQuery({
    queryKey: ["evalHistory"],
    queryFn: getEvalHistory,
    enabled,
    staleTime: 120_000,
  });
}
