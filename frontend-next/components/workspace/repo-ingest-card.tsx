"use client";

import { useState } from "react";
import { Loader2, Search, Zap } from "lucide-react";
import { toast } from "sonner";
import { ingest } from "@/lib/api";
import { ApiError } from "@/lib/types";

type RepoIngestCardProps = {
  onIngestStarted: (jobId: string) => void;
  disabled?: boolean;
};

export function RepoIngestCard({ onIngestStarted, disabled }: RepoIngestCardProps) {
  const [url, setUrl] = useState("");
  const [urlError, setUrlError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit() {
    const repoUrl = url.trim();

    if (!repoUrl) return;

    // Support extracting repo from typical input (e.g. github.com/owner/repo or https://...)
    let cleanUrl = repoUrl;
    if (!cleanUrl.startsWith("http://") && !cleanUrl.startsWith("https://")) {
      cleanUrl = `https://${cleanUrl}`;
    }

    if (!cleanUrl.includes("github.com/")) {
      setUrlError("Please enter a valid GitHub repository URL");
      return;
    }

    setUrlError("");
    setLoading(true);
    try {
      // Defaulting to "main" ref inside the inline form
      const res = await ingest(cleanUrl, "main");
      toast.success("Repository ingestion started");
      onIngestStarted(res.job_id);
      setUrl("");
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Ingestion request failed";
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="w-full max-w-2xl mx-auto">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
        className="relative"
      >
        {/* Absolutely positioned gradient blur behind the input box */}
        <div className="absolute -inset-px rounded-2xl bg-gradient-to-r from-primary/40 via-transparent to-primary/20 opacity-70 blur-md pointer-events-none" />

        {/* Ingest Bar (h-16, rounded-2xl) */}
        <div className="relative flex h-16 w-full items-center justify-between gap-3 rounded-2xl border border-border/40 bg-surface/90 backdrop-blur-md px-4 shadow-elevated focus-within:border-primary/50 focus-within:ring-2 focus-within:ring-primary/20 transition-all duration-200">
          <Search className="h-4 w-4 text-muted-foreground shrink-0 ml-2" />
          <input
            type="text"
            placeholder="github.com/owner/repo  or paste a clone URL..."
            value={url}
            onChange={(e) => {
              setUrl(e.target.value);
              setUrlError("");
            }}
            disabled={disabled || loading}
            aria-invalid={Boolean(urlError)}
            className="flex-1 bg-transparent border-0 outline-none text-foreground placeholder:text-muted-foreground/60 text-sm font-mono focus:ring-0 py-2"
          />
          <button
            type="submit"
            disabled={disabled || loading || !url.trim()}
            className="bg-primary hover:brightness-110 disabled:opacity-40 disabled:hover:brightness-100 text-primary-foreground h-11 px-5 rounded-xl flex items-center justify-center gap-1.5 font-semibold glow-primary active:scale-[0.98] transition-all duration-200 cursor-pointer select-none"
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Zap className="h-3.5 w-3.5 fill-current" />
            )}
            <span>Ingest</span>
          </button>
        </div>

        {urlError && (
          <p className="text-xs text-error mt-2 ml-4 animate-slide-up" role="alert">
            {urlError}
          </p>
        )}
      </form>

      {/* Live Pipeline Status dot */}
      <div className="flex items-center justify-center gap-2 mt-4 text-[11px] text-muted-foreground font-medium select-none">
        <span className="relative flex h-1.5 w-1.5">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success opacity-75"></span>
          <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-success"></span>
        </span>
        <span>Live pipeline &middot; Avg Ingest ~ 3m 40s for 200k LOC</span>
      </div>
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
