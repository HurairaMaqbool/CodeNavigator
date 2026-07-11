"use client";

import { motion } from "framer-motion";
import { FolderGit2 } from "lucide-react";
import { EmptyState } from "@/components/shared/empty-state";
import { PanelErrorBoundary } from "@/components/shared/error-boundary";
import { useApp } from "@/lib/context/app-context";
import { repoIsReady } from "@/lib/constants";
import { useBackendOnline } from "@/lib/hooks/use-backend-health";
import { useRepoStatus } from "@/lib/hooks/use-repo-status";
import { AppShell } from "@/components/layout/app-shell";
import { useIngestHandler, RepoIngestCard } from "@/components/workspace/repo-ingest-card";
import { StatusPanel } from "@/components/workspace/status-panel";
import { ChatPanel } from "@/components/workspace/chat-panel";
import { CallGraphPanel } from "@/components/workspace/call-graph-panel";

export default function WorkspacePage() {
  const { repoId, setRepoId } = useApp();
  const { online: backendOnline, offline: backendOffline } = useBackendOnline();
  const status = useRepoStatus(repoId);
  const ready = status.data ? repoIsReady(status.data) : false;

  const handleQuickStart = useIngestHandler(setRepoId, Boolean(backendOnline));

  return (
    <AppShell onQuickStart={(url, ref) => void handleQuickStart(url, ref)}>
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25 }}
        className="space-y-6"
      >
        <div className="flex flex-wrap gap-2">
          {["Hybrid RAG", "Live agent steps", "Verified citations", "RAGAS eval"].map(
            (chip) => (
              <span
                key={chip}
                className="rounded-full border border-primary/30 bg-primary-tint px-3 py-1 text-xs font-medium text-primary"
              >
                {chip}
              </span>
            ),
          )}
        </div>

        <RepoIngestCard
          onIngestStarted={setRepoId}
          disabled={backendOffline}
        />

        {!repoId ? (
          <EmptyState
            icon={<FolderGit2 className="h-10 w-10" />}
            title="Ingest a repository to begin"
            description="Paste a public GitHub URL above, or pick a Quick start repo in the sidebar. Chat, diagrams, and eval unlock once indexing finishes."
          />
        ) : (
          <div className="grid gap-6 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <PanelErrorBoundary title="Chat panel error">
                <ChatPanel key={repoId} repoId={repoId} ready={ready} />
              </PanelErrorBoundary>
            </div>
            <div className="space-y-6">
              <StatusPanel
                data={status.data}
                isLoading={status.isLoading}
                isError={status.isError}
                error={status.error}
                onRetry={() => void status.refetch()}
              />
              <PanelErrorBoundary title="Call graph error">
                <CallGraphPanel key={repoId} repoId={repoId} ready={ready} />
              </PanelErrorBoundary>
            </div>
          </div>
        )}
      </motion.div>
    </AppShell>
  );
}
