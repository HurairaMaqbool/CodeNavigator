"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { GitBranchPlus } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { PanelErrorBoundary } from "@/components/shared/error-boundary";
import { SectionHeader } from "@/components/shared/section-header";
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
  const ready = status.data ? repoIsReady(status.data) : false;
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
    if (!status.isLoading && status.data && !repoIsReady(status.data)) {
      router.replace("/onboarding");
    }
  }, [repoId, status.isLoading, status.data, router]);

  if (!mounted || !repoId || status.isLoading || !ready) {
    return (
      <AppShell onQuickStart={(url, ref) => void handleQuickStart(url, ref)}>
        <div className="page-enter">
          <ScreenSkeleton cards={2} />
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell onQuickStart={(url, ref) => void handleQuickStart(url, ref)}>
      <div className="page-enter space-y-8">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <SectionHeader
            title="Chat"
            caption="Ask about architecture, classes, and call flows — answers include verifiable file citations."
            className="mb-0"
          />
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              clearSession();
              router.push("/onboarding");
            }}
          >
            <GitBranchPlus className="h-4 w-4" />
            New repository
          </Button>
        </div>

        <div className="w-full">
          <PanelErrorBoundary title="Chat panel error">
            <ChatPanel key={repoId} repoId={repoId} ready={ready} />
          </PanelErrorBoundary>
        </div>
      </div>
    </AppShell>
  );
}
