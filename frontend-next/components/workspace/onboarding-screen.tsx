"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, FolderGit2, GitBranch, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { BRAND, QUICK_START_REPOS, repoIsReady } from "@/lib/constants";
import { useApp } from "@/lib/context/app-context";
import { useBackendOnline } from "@/lib/hooks/use-backend-health";
import { useRepoStatus } from "@/lib/hooks/use-repo-status";
import { useIngestFlow } from "@/lib/hooks/use-ingest-flow";
import { cn } from "@/lib/utils";
import { LogoMark } from "@/components/brand/logo-mark";
import { EmptyState } from "@/components/shared/empty-state";
import { SectionHeader } from "@/components/shared/section-header";
import { Button } from "@/components/ui/button";
import { RepoIngestCard } from "./repo-ingest-card";
import { StatusPanel } from "./status-panel";

export function OnboardingScreen() {
  const router = useRouter();
  const { repoId, setRepoId } = useApp();
  const { online: backendOnline, offline: backendOffline } = useBackendOnline();
  const status = useRepoStatus(repoId);
  const ready = status.data ? repoIsReady(status.data) : false;
  const failed = status.data?.status === "failed";
  const indexing = Boolean(repoId) && !ready && !failed;
  const handleQuickStart = useIngestFlow();
  const sawIndexing = useRef(false);

  useEffect(() => {
    if (repoId && !ready && !failed) sawIndexing.current = true;
  }, [repoId, ready, failed]);

  useEffect(() => {
    if (!ready || !repoId || !sawIndexing.current) return;
    sawIndexing.current = false;
    toast.success("Repository indexed — opening chat");
    const timer = window.setTimeout(() => router.replace("/chat"), 1000);
    return () => window.clearTimeout(timer);
  }, [ready, repoId, router]);

  return (
    <div className="page-enter mx-auto flex w-full max-w-xl flex-col gap-8 py-4">
      <div className="text-center">
        <div className="mx-auto mb-6 relative flex h-16 w-16 items-center justify-center rounded-2xl border border-border bg-surface-raised/40 backdrop-blur-md shadow-elev-2 before:absolute before:inset-0 before:rounded-2xl before:bg-gradient-to-tr before:from-primary/10 before:to-transparent before:opacity-80">
          <LogoMark size="lg" className="relative z-10 text-primary drop-shadow-[0_0_12px_rgba(99,102,241,0.25)]" />
        </div>
        <h1 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl leading-tight">
          {BRAND.tagline}
        </h1>
        <p className="mx-auto mt-3 max-w-md text-sm leading-relaxed text-muted-foreground">
          Connect a GitHub repository. We clone, parse, and index it so you can
          ask precise questions with file-level citations.
        </p>
      </div>

      {!repoId || failed ? (
        <>
          <RepoIngestCard
            onIngestStarted={(jobId) => setRepoId(jobId)}
            disabled={backendOffline}
          />

          <div className="card-panel">
            <SectionHeader
              title="Quick start"
              caption="Index a well-known open-source project"
              className="mb-4"
            />
            <div className="grid gap-3 sm:grid-cols-3">
              {QUICK_START_REPOS.map((repo) => (
                <button
                  key={repo.url}
                  type="button"
                  disabled={!backendOnline}
                  onClick={() => void handleQuickStart(repo.url, repo.ref)}
                  className={cn(
                    "flex flex-col items-start gap-2.5 rounded-xl border border-border bg-surface-raised/40 p-4 text-left transition-all duration-200 cursor-pointer",
                    "hover:border-primary/25 hover:bg-primary-tint/30 hover:shadow-elev-1",
                    "disabled:opacity-45 disabled:pointer-events-none active:scale-[0.98]"
                  )}
                >
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <GitBranch className="h-4 w-4" />
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-foreground">{repo.label}</p>
                    <p className="text-[10px] text-muted-foreground mt-0.5">Click to index</p>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </>
      ) : ready ? (
        <EmptyState
          icon={<FolderGit2 className="h-5 w-5" />}
          title="Repository ready"
          description="Your codebase is indexed. Open chat to explore architecture, symbols, and flows."
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <Button onClick={() => router.push("/chat")}>
                Open chat
                <ArrowRight className="h-4 w-4" />
              </Button>
              <Button variant="secondary" onClick={() => setRepoId(null)}>
                Connect another repo
              </Button>
            </div>
          }
        />
      ) : (
        <div className="card-surface p-6">
          <SectionHeader
            title="Indexing in progress"
            caption="Usually completes within a few minutes. You'll be redirected automatically."
            className="mb-4"
          />
          <StatusPanel
            data={status.data}
            isLoading={status.isLoading}
            isError={status.isError}
            error={status.error}
            onRetry={() => void status.refetch()}
          />
          {indexing && (
            <p className="mt-5 flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              Cloning and building search index…
            </p>
          )}
        </div>
      )}
    </div>
  );
}
