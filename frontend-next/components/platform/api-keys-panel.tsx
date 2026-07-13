"use client";

import { useState } from "react";
import { Loader2, Plus, Trash2 } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  createPlatformApiKey,
  listPlatformApiKeys,
  revokePlatformApiKey,
} from "@/lib/api";
import { ApiError } from "@/lib/types";
import { SectionHeader } from "@/components/shared/section-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";

export function ApiKeysPanel({ enabled }: { enabled: boolean }) {
  const qc = useQueryClient();
  const [label, setLabel] = useState("platform-key");
  const [revealedSecret, setRevealedSecret] = useState<string | null>(null);

  const keys = useQuery({
    queryKey: ["platformApiKeys"],
    queryFn: listPlatformApiKeys,
    enabled,
  });

  const createMut = useMutation({
    mutationFn: () => createPlatformApiKey(label.trim() || "platform-key"),
    onSuccess: (data) => {
      setRevealedSecret(data.api_key);
      toast.success("API key created — copy it now; it won't be shown again.");
      void qc.invalidateQueries({ queryKey: ["platformApiKeys"] });
      void qc.invalidateQueries({ queryKey: ["audit"] });
    },
    onError: (e) => {
      toast.error(e instanceof ApiError ? e.message : "Failed to create key");
    },
  });

  const revokeMut = useMutation({
    mutationFn: (prefix: string) => revokePlatformApiKey(prefix),
    onSuccess: () => {
      toast.success("API key revoked");
      void qc.invalidateQueries({ queryKey: ["platformApiKeys"] });
      void qc.invalidateQueries({ queryKey: ["audit"] });
    },
    onError: (e) => {
      toast.error(e instanceof ApiError ? e.message : "Failed to revoke key");
    },
  });



  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 5;

  const uniqueKeys = keys.data ?? [];
  const totalPages = Math.max(1, Math.ceil(uniqueKeys.length / itemsPerPage));
  const paginatedKeys = uniqueKeys.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  );

  return (
    <div className="card-panel space-y-4">
      <SectionHeader
        title="API keys"
        caption="Keys are stored hashed; only prefixes are listed. Full secret shown once on create."
      />

      {revealedSecret && (
        <div className="rounded-lg border border-warning/30 bg-warning/10 px-4 py-3 text-sm text-warning">
          <p className="font-medium">New key — copy now</p>
          <code className="mt-2 block break-all text-xs">{revealedSecret}</code>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mt-2"
            onClick={() => {
              void navigator.clipboard.writeText(revealedSecret);
              toast.success("Copied to clipboard");
            }}
          >
            Copy key
          </Button>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <Input
          placeholder="Key label"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          className="max-w-xs"
          aria-label="API key label"
        />
        <Button
          type="button"
          disabled={createMut.isPending}
          onClick={() => createMut.mutate()}
        >
          {createMut.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Plus className="h-4 w-4" />
          )}
          Create key
        </Button>
      </div>

      {keys.isLoading ? (
        <Skeleton className="h-24 w-full" />
      ) : keys.isError ? (
        <p className="text-sm text-error">
          {keys.error instanceof ApiError ? keys.error.message : "Failed to load keys"}
        </p>
      ) : uniqueKeys.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No org-scoped keys yet (legacy env key may still work).
        </p>
      ) : (
        <div className="space-y-2">
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Prefix</th>
                  <th>Label</th>
                  <th>Created</th>
                  <th>Status</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {paginatedKeys.map((row) => (
                  <tr key={row.key_prefix}>
                    <td className="font-mono text-xs">{row.key_prefix}</td>
                    <td>{row.label}</td>
                    <td className="text-xs text-muted-foreground">
                      {row.created_at
                        ? new Date(row.created_at).toLocaleString()
                        : "—"}
                    </td>
                    <td>
                      <Badge variant={row.active ? "success" : "muted"}>
                        {row.active ? "Active" : "Revoked"}
                      </Badge>
                    </td>
                    <td>
                      {row.active && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          disabled={revokeMut.isPending}
                          onClick={() =>
                            revokeMut.mutate(row.key_prefix.replace("…", ""))
                          }
                          aria-label="Revoke key"
                        >
                          <Trash2 className="h-4 w-4 text-error" />
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between border border-border bg-surface-raised px-4 py-2 rounded-lg">
              <p className="text-xs text-muted-foreground">
                Showing {((currentPage - 1) * itemsPerPage) + 1} to {Math.min(currentPage * itemsPerPage, uniqueKeys.length)} of {uniqueKeys.length} keys
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
      )}
    </div>
  );
}
