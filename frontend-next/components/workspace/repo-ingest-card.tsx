"use client";

import { useState } from "react";
import { FolderGit2, Loader2 } from "lucide-react";
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
    <div className="rounded-xl border border-border bg-surface p-5 shadow-sm">
      <SectionHeader
        title="Repository"
        caption="Paste a public GitHub URL or use Quick start in the sidebar"
      />
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <div className="space-y-2">
          <Label htmlFor="repo-url">GitHub URL</Label>
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
          />
          {urlError && (
            <p id="url-error" className="text-sm text-error" role="alert">
              {urlError}
            </p>
          )}
        </div>
        <div className="space-y-2">
          <Label htmlFor="branch">Branch</Label>
          <Input
            id="branch"
            placeholder="main"
            value={branch}
            onChange={(e) => setBranch(e.target.value)}
            disabled={disabled || loading}
          />
        </div>
        <Button type="submit" disabled={disabled || loading} className="w-full sm:w-auto">
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <FolderGit2 className="h-4 w-4" />
          )}
          Ingest
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
