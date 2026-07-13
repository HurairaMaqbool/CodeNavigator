"use client";

import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useApp } from "@/lib/context/app-context";
import { invalidateRepoQueries } from "@/lib/repo-sync";

/**
 * Event-driven cross-screen sync: when active repo changes, invalidate stale
 * React Query caches so Chat/Eval/Connect refetch on navigation.
 */
export function RepoSyncBridge() {
  const { repoId } = useApp();
  const qc = useQueryClient();
  const prevRef = useRef<string | null>(null);

  useEffect(() => {
    const prev = prevRef.current;
    if (prev === repoId) return;

    if (prev) invalidateRepoQueries(qc, prev);
    if (repoId) invalidateRepoQueries(qc, repoId);

    prevRef.current = repoId;
  }, [repoId, qc]);

  return null;
}
