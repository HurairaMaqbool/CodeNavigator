"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, FolderGit2, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { ingest } from "@/lib/api";
import { ApiError } from "@/lib/types";
import { SectionHeader } from "@/components/shared/section-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type RepoIngestCardProps = {
  onIngestStarted: (jobId: string) => void;
  disabled?: boolean;
};

export function RepoIngestCard({ onIngestStarted, disabled }: RepoIngestCardProps) {
  const [url, setUrl] = useState("");
  const [branch, setBranch] = useState("main");
  const [urlError, setUrlError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);

  async function submit(targetUrl?: string, targetRef?: string) {
    const repoUrl = (targetUrl ?? url).trim();
    const ref = targetRef ?? (branch.trim() || undefined);

    if (!repoUrl.startsWith("https://github.com/")) {
      setUrlError("Enter a valid public GitHub URL (https://github.com/owner/repo)");
      return;
    }
    setUrlError("");
    setLoading(true);
    try {
      const res = await ingest(repoUrl, ref);
      toast.success("Ingestion started");
      onIngestStarted(res.job_id);
      if (!targetUrl) setUrl("");
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Ingest failed";
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card-panel">
      <SectionHeader
        title="Connect repository"
        caption="Paste a public GitHub URL to begin indexing"
        className="mb-4"
      />
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <div className="space-y-2">
          <Label htmlFor="repo-url" className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">GitHub URL</Label>
          <Input
            id="repo-url"
            placeholder="https://github.com/owner/repo"
            value={url}
            onChange={(e) => {
              setUrl(e.target.value);
              setUrlError("");
            }}
            disabled={disabled || loading}
            aria-invalid={Boolean(urlError)}
            aria-describedby={urlError ? "url-error" : undefined}
            className="bg-surface/50 border-border hover:border-border-strong focus:border-primary transition-colors"
          />
          {urlError && (
            <p id="url-error" className="text-xs text-error mt-1" role="alert">
              {urlError}
            </p>
          )}
        </div>

        <div>
          <button
            type="button"
            className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors cursor-pointer select-none"
            onClick={() => setShowAdvanced((v) => !v)}
          >
            {showAdvanced ? (
              <ChevronUp className="h-3.5 w-3.5" />
            ) : (
              <ChevronDown className="h-3.5 w-3.5" />
            )}
            Advanced settings
          </button>
          
          {showAdvanced && (
            <div className="space-y-2 mt-3 pt-3 border-t border-border/40 page-enter">
              <Label htmlFor="branch" className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Branch / Ref</Label>
              <Input
                id="branch"
                placeholder="main"
                value={branch}
                onChange={(e) => setBranch(e.target.value)}
                disabled={disabled || loading}
                className="bg-surface/50 border-border hover:border-border-strong focus:border-primary transition-colors"
              />
            </div>
          )}
        </div>

        <Button type="submit" disabled={disabled || loading} className="w-full sm:w-auto font-semibold active:scale-[0.98]">
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <FolderGit2 className="h-4 w-4" />
          )}
          Ingest repository
        </Button>
      </form>
    </div>
  );
}

export function useIngestHandler(
  setRepoId: (id: string) => void,
  backendOnline: boolean,
) {
  return async (repoUrl: string, ref: string) => {
    if (!backendOnline) {
      toast.error("Backend offline — start uvicorn on port 8000");
      return;
    }
    try {
      const res = await ingest(repoUrl, ref);
      setRepoId(res.job_id);
      toast.success("Quick start ingestion started");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Ingest failed");
    }
  };
}
