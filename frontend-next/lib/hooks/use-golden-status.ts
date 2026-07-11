"use client";

import { useQuery } from "@tanstack/react-query";
import { getGoldenStatus } from "@/lib/api";

export function useGoldenStatus(enabled = true) {
  return useQuery({
    queryKey: ["goldenStatus"],
    queryFn: getGoldenStatus,
    enabled,
    staleTime: 60_000,
  });
}
