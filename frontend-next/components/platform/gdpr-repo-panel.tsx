"use client";

import { useState } from "react";
import { Download, Loader2, Trash2 } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  exportPlatformRepo,
  ingest,
  listPlatformRepos,
  purgePlatformRepo,
} from "@/lib/api";
import { ApiError } from "@/lib/types";
import { invalidateAfterRepoMutation } from "@/lib/repo-sync";
import { useApp } from "@/lib/context/app-context";
import { cn } from "@/lib/utils";
import { SectionHeader } from "@/components/shared/section-header";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";

function downloadJson(filename: string, data: unknown) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function formatRepoChunkCount(row: {
  chroma_chunks?: number | null;
  chunks_created?: number | null;
  sync_status?: string | null;
}): string {
  const chroma = row.chroma_chunks ?? null;
  const created = row.chunks_created ?? null;
  const statusLower = (row.sync_status ?? "").toLowerCase();
  const isIndexing =
    statusLower === "indexing" ||
    statusLower === "processing" ||
    statusLower === "cloning" ||
    statusLower === "parsing";

  if (chroma != null && created != null) {
    return `${chroma} / ${created}`;
  }
  if (chroma != null) {
    return `${chroma} / ${isIndexing ? "calculating…" : "—"}`;
  }
  if (created != null) {
    return String(created);
  }
  return isIndexing ? "calculating…" : "—";
}

export function GdprRepoPanel({ enabled }: { enabled: boolean }) {
  const qc = useQueryClient();
  const { repoId: activeRepoId, clearSession } = useApp();
  const [selectedId, setSelectedId] = useState("");
  const [confirmText, setConfirmText] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 5;

  const repos = useQuery({
    queryKey: ["platformRepos"],
    queryFn: listPlatformRepos,
    enabled,
    retry: 3,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10000),
  });

  const exportMut = useMutation({
    mutationFn: (repoId: string) => exportPlatformRepo(repoId),
    onSuccess: (data, repoId) => {
      downloadJson(`export-${repoId.slice(0, 12)}.json`, data);
      toast.success("Export downloaded");
    },
    onError: (e) => {
      toast.error(e instanceof ApiError ? e.message : "Export failed");
    },
  });

  const purgeMut = useMutation({
    mutationFn: (repoId: string) => purgePlatformRepo(repoId),
    onSuccess: (_data, purgedId) => {
      toast.success("Repository purged");
      setConfirmText("");
      setSelectedId("");
      invalidateAfterRepoMutation(qc, purgedId);
      void qc.invalidateQueries({ queryKey: ["audit"] });
      if (activeRepoId === purgedId) clearSession();
    },
    onError: (e) => {
      toast.error(e instanceof ApiError ? e.message : "Purge failed");
    },
  });

  const reindexMut = useMutation({
    mutationFn: (row: { repo_url: string; ref: string; repo_id: string }) =>
      ingest(row.repo_url, row.ref, true),
    onSuccess: (_data, row) => {
      toast.success("Re-index started — index status will sync across screens");
      invalidateAfterRepoMutation(qc, row.repo_id);
      void qc.invalidateQueries({ queryKey: ["audit"] });
    },
    onError: (e) => {
      toast.error(e instanceof ApiError ? e.message : "Re-index failed");
    },
  });

  const active = repos.data?.find((r) => r.repo_id === selectedId);

  const uniqueRepos = repos.data ?? [];
  const totalPages = Math.max(1, Math.ceil(uniqueRepos.length / itemsPerPage));
  const paginatedRepos = uniqueRepos.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  );

  return (
    <div className="card-surface space-y-4 p-6">
      <SectionHeader
        title="Repository data (GDPR)"
        caption="Export metadata or permanently purge clone, vectors, and indexes"
      />
      <Alert kind="warning">
        Purge is irreversible. Type the repository ID exactly to confirm deletion.
      </Alert>

      {repos.isLoading ? (
        <Skeleton className="h-24 w-full" />
      ) : repos.isError ? (
        <p className="text-sm text-error">
          {repos.error instanceof ApiError ? repos.error.message : "Failed to load repos"}
        </p>
      ) : uniqueRepos.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No repositories for this organization. Ingest a repo from the Connect tab first.
        </p>
      ) : (
        <>
          <div className="space-y-2">
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Repository</th>
                    <th>Status</th>
                    <th>Chunks</th>
                    <th>Index</th>
                    <th aria-label="Actions" />
                  </tr>
                </thead>
                <tbody>
                  {paginatedRepos.map((row) => (
                    <tr
                      key={row.repo_id}
                      className={cn(
                        selectedId === row.repo_id && "row-active",
                      )}
                    >
                      <td>
                        <p className="font-medium truncate max-w-[200px]">{row.repo_url || row.repo_id}</p>
                        <p className="font-mono text-xs text-muted-foreground">
                          {row.repo_id.slice(0, 16)}…
                        </p>
                      </td>
                      <td>
                        <span className={cn(
                          "badge",
                          row.sync_status === "completed" || row.sync_status === "ready"
                            ? "badge-success"
                            : row.sync_status === "failed"
                              ? "badge-error"
                              : "badge-warning animate-pulse"
                        )}>
                          {row.sync_status}
                        </span>
                      </td>
                      <td>
                        {formatRepoChunkCount(row)}
                      </td>
                      <td>
                        {row.index_integrity_ok === false ? (
                          <span className="badge badge-error">Mismatch</span>
                        ) : row.index_integrity_ok === true ? (
                          <span className="badge badge-success">OK</span>
                        ) : (
                          <span className="badge badge-neutral">—</span>
                        )}
                      </td>
                      <td>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => setSelectedId(row.repo_id)}
                        >
                          Select
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {totalPages > 1 && (
              <div className="flex items-center justify-between border border-border bg-surface-raised px-4 py-2 rounded-lg">
                <p className="text-xs text-muted-foreground">
                  Showing {((currentPage - 1) * itemsPerPage) + 1} to {Math.min(currentPage * itemsPerPage, uniqueRepos.length)} of {uniqueRepos.length} repositories
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-7 text-xs px-2"
                    disabled={currentPage === 1}
                    onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                  >
                    Previous
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-7 text-xs px-2"
                    disabled={currentPage === totalPages}
                    onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
                  >
                    Next
                  </Button>
                </div>
              </div>
            )}
          </div>

          {active && (
            <div className="space-y-3 rounded-lg border border-border p-4">
              <p className="text-sm">
                Selected: <code className="text-xs">{active.repo_id}</code>
              </p>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="outline"
                  disabled={exportMut.isPending}
                  onClick={() => exportMut.mutate(active.repo_id)}
                >
                  {exportMut.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Download className="h-4 w-4" />
                  )}
                  Export JSON
                </Button>
                {active.index_integrity_ok === false && active.repo_url && (
                  <Button
                    type="button"
                    disabled={reindexMut.isPending}
                    onClick={() =>
                      reindexMut.mutate({
                        repo_url: active.repo_url,
                        ref: active.ref || "main",
                        repo_id: active.repo_id,
                      })
                    }
                  >
                    {reindexMut.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : null}
                    Force re-index
                  </Button>
                )}
              </div>
              <div className="space-y-2 border-t border-border pt-3">
                <p className="text-xs text-muted-foreground">
                  Type <code>{active.repo_id}</code> to confirm purge:
                </p>
                <Input
                  value={confirmText}
                  onChange={(e) => setConfirmText(e.target.value)}
                  placeholder="Repository ID"
                  aria-label="Confirm purge repository ID"
                />
                <Button
                  type="button"
                  variant="destructive"
                  disabled={
                    confirmText !== active.repo_id || purgeMut.isPending
                  }
                  onClick={() => purgeMut.mutate(active.repo_id)}
                >
                  {purgeMut.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Trash2 className="h-4 w-4" />
                  )}
                  Purge repository
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
