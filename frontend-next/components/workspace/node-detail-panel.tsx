"use client";

import { useEffect, useState } from "react";
import { Code, FileText, Loader2, Network } from "lucide-react";
import { getFileSnippet, type FileSnippetResponse } from "@/lib/api";

type NodeDetailPanelProps = {
  repoId: string;
  symbolName: string | null;
  filePath: string | null;
  type: string | null;
  startLine: number | null;
  endLine: number | null;
  onClose?: () => void;
};

export function NodeDetailPanel({
  repoId,
  symbolName,
  filePath,
  type,
  startLine,
  endLine,
  onClose,
}: NodeDetailPanelProps) {
  const [loading, setLoading] = useState(false);
  const [snippet, setSnippet] = useState<FileSnippetResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!symbolName || !filePath) {
      setSnippet(null);
      return;
    }

    let active = true;
    async function loadSnippet() {
      setLoading(true);
      setError(null);
      try {
        const res = await getFileSnippet(
          repoId,
          filePath,
          startLine ?? undefined,
          endLine ?? undefined
        );
        if (active) {
          setSnippet(res);
        }
      } catch (e) {
        if (active) {
          setError("Failed to load code snippet.");
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    void loadSnippet();
    return () => {
      active = false;
    };
  }, [repoId, symbolName, filePath, startLine, endLine]);

  if (!symbolName) {
    return (
      <div className="card-panel h-full flex flex-col items-center justify-center p-8 text-center text-muted-foreground">
        <Network className="h-10 w-10 mb-3 text-muted/60" />
        <p className="font-semibold text-foreground mb-1">No node selected</p>
        <p className="text-xs">Click on any node in the diagram to inspect its parameters and view code snippets.</p>
      </div>
    );
  }

  return (
    <div className="card-panel h-full flex flex-col overflow-hidden">
      <div className="flex items-center justify-between border-b border-border pb-4 mb-4">
        <div>
          <h3 className="text-base font-semibold text-foreground truncate max-w-[200px]">
            {symbolName}
          </h3>
          <span className="inline-flex items-center rounded-md bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary mt-1">
            {type || "Symbol"}
          </span>
        </div>
        {onClose && (
          <button
            type="button"
            className="text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
            onClick={onClose}
          >
            Close
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto space-y-4 pr-1">
        {/* Metadata Details */}
        <div className="space-y-2.5 text-sm">
          <div className="flex items-start gap-2.5">
            <FileText className="h-4 w-4 text-muted-foreground shrink-0 mt-0.5" />
            <div className="min-w-0">
              <p className="text-xs font-semibold text-muted-foreground">File Path</p>
              <p className="text-foreground text-xs break-all">{filePath}</p>
            </div>
          </div>
          {(startLine !== null && endLine !== null) && (
            <div className="flex items-start gap-2.5">
              <Code className="h-4 w-4 text-muted-foreground shrink-0 mt-0.5" />
              <div>
                <p className="text-xs font-semibold text-muted-foreground">Code Coordinates</p>
                <p className="text-foreground text-xs">
                  Lines {startLine} - {endLine}
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Code Snippet Box */}
        <div className="mt-4 flex-1 flex flex-col min-h-0">
          <p className="text-xs font-semibold text-muted-foreground mb-2">Code Snippet</p>
          
          {loading && (
            <div className="flex-1 min-h-[200px] flex items-center justify-center border border-border rounded-lg bg-surface">
              <Loader2 className="h-5 w-5 animate-spin text-primary" />
            </div>
          )}

          {!loading && error && (
            <div className="p-4 border border-warning/30 bg-warning/10 text-xs text-warning rounded-lg">
              {error}
            </div>
          )}

          {!loading && !error && snippet && (
            <div className="relative flex-1 min-h-[300px] rounded-lg border border-border bg-surface-raised overflow-hidden flex flex-col">
              <div className="flex items-center justify-between border-b border-border bg-muted/40 px-3 py-1.5 text-[11px] text-muted-foreground font-mono">
                <span>{filePath?.split("/").pop()}</span>
                {snippet.start_line && snippet.end_line && (
                  <span>
                    Lines {snippet.start_line}-{snippet.end_line} of {snippet.total_lines}
                  </span>
                )}
              </div>
              <pre className="flex-1 overflow-auto p-4 text-[11px] font-mono leading-normal text-foreground whitespace-pre bg-surface text-left">
                <code>{snippet.code}</code>
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
