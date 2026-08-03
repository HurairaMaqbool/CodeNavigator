"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Box, GitBranchPlus } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { PanelErrorBoundary } from "@/components/shared/error-boundary";
import { Button } from "@/components/ui/button";
import { ScreenSkeleton } from "@/components/ui/skeleton";
import { ChatPanel } from "@/components/workspace/chat-panel";
import { useApp } from "@/lib/context/app-context";
import { repoIsReady } from "@/lib/constants";
import { useIngestFlow } from "@/lib/hooks/use-ingest-flow";
import { useRepoStatus } from "@/lib/hooks/use-repo-status";

export default function ChatPage() {
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  const { repoId, clearSession } = useApp();
  const status = useRepoStatus(repoId);
  const ready = status.data ? repoIsReady(status.data) : true;
  const handleQuickStart = useIngestFlow();

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted) return;
    if (!repoId) {
      router.replace("/onboarding");
      return;
    }
  }, [repoId, mounted, router]);

  if (!mounted || !repoId) {
    return (
      <AppShell>
        <div className="page-enter">
          <ScreenSkeleton cards={2} />
        </div>
      </AppShell>
    );
  }

  // Resolve dynamic display properties for active repo from status.data
  const getRepoDisplayName = () => {
    if (status.data?.repo_id) return status.data.repo_id.slice(0, 16);
    if (repoId.includes("b4f947369301e4e")) return "psf/requests";
    if (repoId.includes("c95ed10bde76")) return "pallets/flask";
    return repoId.slice(0, 16);
  };

  const getRepoVersion = () => {
    if (status.data?.ref) return status.data.ref;
    if (repoId.includes("b4f947369301e4e")) return "v2.31.0";
    if (repoId.includes("c95ed10bde76")) return "v3.0.2";
    return "main";
  };

  const getRepoMeta = () => {
    if (status.data) {
      return `${status.data.files_parsed.toLocaleString()} files · ${status.data.chunks_created.toLocaleString()} chunks`;
    }
    return "Indexed codebase";
  };

  return (
    <AppShell>
      <div className="page-enter space-y-6">
        {/* Sub-Header (below top bar) */}
        <div className="h-14 border-b border-border/40 flex items-center justify-between px-2 select-none">
          {/* Left Side: Repo info, box icon tile, and version chip */}
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-primary/20 bg-accent text-primary shrink-0 shadow-sm">
              <Box className="h-4 w-4 stroke-[2]" />
            </div>
            <span className="text-sm font-bold text-foreground font-display">
              {getRepoDisplayName()}
            </span>
            <span className="rounded bg-accent text-primary px-1.5 py-0.5 font-mono text-[11px] font-semibold border border-primary/10">
              {getRepoVersion()}
            </span>
          </div>

          {/* Right Side: Symbols & Chunks Count Meta */}
          <div className="flex items-center gap-4">
            <span className="hidden sm:inline font-mono text-xs text-muted-foreground">
              {getRepoMeta()}
            </span>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                clearSession();
                router.push("/onboarding");
              }}
              className="h-8 text-xs font-semibold px-2.5 rounded-lg active:scale-95"
            >
              <GitBranchPlus className="h-3.5 w-3.5 mr-1" />
              New repo
            </Button>
          </div>
        </div>

        {/* Conversation Thread Panel */}
        <div className="w-full">
          <PanelErrorBoundary title="Chat panel error">
            <ChatPanel key={repoId} repoId={repoId} ready={ready} />
          </PanelErrorBoundary>
        </div>
      </div>
    </AppShell>
  );
}
