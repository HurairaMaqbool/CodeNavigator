"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Activity,
  ArrowRight,
  Cpu,
  Database,
  FolderGit2,
  GitBranch,
  Loader2,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { toast } from "sonner";
import { repoIsReady } from "@/lib/constants";
import { useApp } from "@/lib/context/app-context";
import { useBackendOnline } from "@/lib/hooks/use-backend-health";
import { useRepoStatus } from "@/lib/hooks/use-repo-status";
import { useIngestFlow } from "@/lib/hooks/use-ingest-flow";
import { cn } from "@/lib/utils";
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
    <div className="page-enter mx-auto flex w-full max-w-[1200px] flex-col gap-12 py-8 relative">
      
      {/* Hero Header Area */}
      <div className="text-center flex flex-col items-center">
        {/* Sparkles Subtitle Chip */}
        <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/25 bg-primary-tint px-3.5 py-1.5 text-[11px] text-primary font-medium tracking-tight mb-5 select-none animate-aurora-drift" style={{ animationDuration: '6s' }}>
          <Sparkles className="h-3.5 w-3.5 fill-current" />
          <span>Semantic code intelligence · RAG-powered</span>
        </div>

        {/* Hero Title */}
        <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight text-foreground leading-[1.1] max-w-2xl font-display">
          Navigate any codebase <br />
          <span className="text-gradient">with clarity.</span>
        </h1>
        
        {/* Hero Caption */}
        <p className="mx-auto mt-4 max-w-xl text-sm md:text-base leading-relaxed text-muted-foreground/80">
          Ingest a Git repository and ask questions with grounded citations,
          call-graph inspection, and evaluated retrieval.
        </p>
      </div>

      {/* Main Action Area */}
      <div className="w-full max-w-2xl mx-auto">
        {!repoId || failed ? (
          <div className="space-y-10">
            {/* Repo Input Box (56px Hero Form) */}
            <RepoIngestCard
              onIngestStarted={(jobId) => setRepoId(jobId)}
              disabled={backendOffline}
            />

            {/* Quick Start Panel */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-bold text-foreground font-display">Quick start</h2>
                  <p className="text-xs text-muted-foreground">Index a well-known open-source repository instantly</p>
                </div>
                <Link
                  href="/chat"
                  className="text-xs font-semibold text-primary hover:text-primary-hover flex items-center gap-1 transition-colors"
                >
                  Browse catalog &rarr;
                </Link>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                {[
                  {
                    label: "psf/requests",
                    url: "https://github.com/psf/requests",
                    ref: "main",
                    stars: "51.2k",
                    version: "v2.31.0",
                    lang: "Python",
                    desc: "A simple, yet elegant HTTP library for Python, built for human beings.",
                    accent: "from-violet-500 to-fuchsia-500",
                  },
                  {
                    label: "pallets/flask",
                    url: "https://github.com/pallets/flask",
                    ref: "main",
                    stars: "66.1k",
                    version: "v3.0.2",
                    lang: "Python",
                    desc: "A lightweight WSGI web application framework in Python.",
                    accent: "from-blue-500 to-cyan-500",
                  },
                  {
                    label: "tiangolo/fastapi",
                    url: "https://github.com/tiangolo/fastapi",
                    ref: "main",
                    stars: "69.3k",
                    version: "v0.110.0",
                    lang: "Python",
                    desc: "Modern, fast, high-performance web framework for building APIs.",
                    accent: "from-emerald-500 to-teal-500",
                  },
                  {
                    label: "vercel/next.js",
                    url: "https://github.com/vercel/next.js",
                    ref: "main",
                    stars: "118.2k",
                    version: "v14.1.0",
                    lang: "TypeScript",
                    desc: "The React Framework for the Web. Used by some of the world's largest companies.",
                    accent: "from-amber-500 to-rose-500",
                  },
                ].map((repo) => (
                  <button
                    key={repo.url}
                    type="button"
                    disabled={!backendOnline}
                    onClick={() => void handleQuickStart(repo.url, repo.ref)}
                    className={cn(
                      "group relative flex flex-col justify-between rounded-2xl border border-border bg-surface/70 backdrop-blur-md p-5 overflow-hidden text-left transition-all duration-200 cursor-pointer shadow-elev-1",
                      "hover:border-primary/40 hover:bg-surface hover:-translate-y-[1px]",
                      "disabled:opacity-45 disabled:pointer-events-none active:scale-[0.98]"
                    )}
                  >
                    {/* Colored Aura Orb (Revels on hover) */}
                    <div className={cn(
                      "absolute -top-16 -right-16 h-40 w-40 rounded-full bg-gradient-to-br blur-2xl opacity-40 transition-opacity duration-300 group-hover:opacity-80 pointer-events-none",
                      repo.accent
                    )} />

                    {/* Card Header Row */}
                    <div className="relative z-10 flex w-full items-center justify-between gap-2 select-none">
                      <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-surface-raised border border-border/40 text-primary transition-transform duration-200 group-hover:scale-105">
                        <FolderGit2 className="h-4 w-4" />
                      </div>
                      <span className="font-mono text-[10px] font-semibold text-muted-foreground bg-surface-raised/40 px-2 py-0.5 rounded border border-border/30">
                        ★ {repo.stars}
                      </span>
                    </div>

                    {/* Title & Desc */}
                    <div className="relative z-10 mt-4 flex-1">
                      <h3 className="font-display font-semibold text-base text-foreground group-hover:text-primary transition-colors">
                        {repo.label}
                      </h3>
                      <p className="text-xs text-muted-foreground/80 mt-1.5 min-h-[3em] leading-relaxed">
                        {repo.desc}
                      </p>
                    </div>

                    {/* Footer Row */}
                    <div className="relative z-10 mt-5 border-t border-border/20 pt-3 flex w-full items-center justify-between select-none">
                      <div className="flex items-center gap-2">
                        <span className="bg-accent text-primary px-2 py-0.5 rounded font-mono text-[10px] font-semibold">
                          {repo.version}
                        </span>
                        <span className="text-[10px] text-tertiary font-medium font-sans">
                          {repo.lang}
                        </span>
                      </div>
                      {/* Arrow slides in from left on hover */}
                      <span className="text-primary text-xs font-semibold transform translate-x-2 opacity-0 group-hover:translate-x-0 group-hover:opacity-100 transition-all duration-200">
                        Index &rarr;
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : ready ? (
          <EmptyState
            icon={<FolderGit2 className="h-5 w-5" />}
            title="Repository ready"
            description="Your codebase is indexed. Open chat to explore architecture, symbols, and flows."
            action={
              <div className="flex flex-wrap justify-center gap-3 mt-4">
                <Button onClick={() => router.push("/chat")} className="shadow-glow">
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
          <div className="card-surface p-6 shadow-xl">
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
              <p className="mt-5 flex items-center gap-2 text-sm text-muted-foreground font-mono">
                <Loader2 className="h-4 w-4 animate-spin text-primary" aria-hidden />
                Cloning and building search index…
              </p>
            )}
          </div>
        )}
      </div>

      {/* Bottom Metric Cards (Workspace Stats) */}
      <div className="grid gap-4 grid-cols-2 lg:grid-cols-4 mt-8 w-full border-t border-border/20 pt-10">
        {/* Stats Card 1 */}
        <div className="card-surface group flex flex-col justify-between p-5 transition-all duration-200 hover:border-primary/30 hover:-translate-y-[1px]">
          <div className="flex justify-between items-start gap-2">
            <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider font-sans">
              REPOS INDEXED
            </span>
            <Database className="h-4 w-4 text-muted-foreground group-hover:text-primary transition-colors" />
          </div>
          <div className="mt-4">
            <span className="text-2xl font-bold tracking-tight text-foreground font-mono tabular-nums">
              12.4k
            </span>
            <p className="text-[10px] text-success font-medium mt-1">
              +3% this week
            </p>
          </div>
        </div>

        {/* Stats Card 2 */}
        <div className="card-surface group flex flex-col justify-between p-5 transition-all duration-200 hover:border-primary/30 hover:-translate-y-[1px]">
          <div className="flex justify-between items-start gap-2">
            <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider font-sans">
              QUERIES / MIN
            </span>
            <Activity className="h-4 w-4 text-muted-foreground group-hover:text-primary transition-colors" />
          </div>
          <div className="mt-4">
            <span className="text-2xl font-bold tracking-tight text-foreground font-mono tabular-nums">
              3,281
            </span>
            <p className="text-[10px] text-success font-medium mt-1">
              +12 vs last hour
            </p>
          </div>
        </div>

        {/* Stats Card 3 */}
        <div className="card-surface group flex flex-col justify-between p-5 transition-all duration-200 hover:border-primary/30 hover:-translate-y-[1px]">
          <div className="flex justify-between items-start gap-2">
            <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider font-sans">
              UPTIME
            </span>
            <ShieldCheck className="h-4 w-4 text-muted-foreground group-hover:text-primary transition-colors" />
          </div>
          <div className="mt-4">
            <span className="text-2xl font-bold tracking-tight text-foreground font-mono tabular-nums">
              99.98%
            </span>
            <p className="text-[10px] text-muted-foreground font-medium mt-1">
              SLO healthy
            </p>
          </div>
        </div>

        {/* Stats Card 4 */}
        <div className="card-surface group flex flex-col justify-between p-5 transition-all duration-200 hover:border-primary/30 hover:-translate-y-[1px]">
          <div className="flex justify-between items-start gap-2">
            <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider font-sans">
              NODES
            </span>
            <Cpu className="h-4 w-4 text-muted-foreground group-hover:text-primary transition-colors" />
          </div>
          <div className="mt-4">
            <span className="text-2xl font-bold tracking-tight text-foreground font-mono tabular-nums">
              128
            </span>
            <p className="text-[10px] text-muted-foreground font-medium mt-1">
              auto-scaling active
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
