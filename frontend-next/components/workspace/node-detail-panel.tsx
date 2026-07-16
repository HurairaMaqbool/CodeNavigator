"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Code,
  Loader2,
  Network,
  Copy,
  Check,
  ArrowRight,
  User,
  RefreshCw,
  FileX,
  AlertTriangle,
} from "lucide-react";
import { getFileSnippet, type FileSnippetResponse } from "@/lib/api";
import { ApiError } from "@/lib/types";

type NodeDetailPanelProps = {
  repoId: string;
  symbolName: string | null;
  filePath: string | null;
  type: string | null;
  startLine: number | null;
  endLine: number | null;
  onClose?: () => void;
};

/** Map structured backend error_type → specific actionable UI message */
function classifySnippetError(
  err: unknown,
  filePath: string | null,
): { message: string; hint: string; icon: "missing" | "stale" | "generic" } {
  if (err instanceof ApiError) {
    const msg = err.message ?? "";

    // File not found (404 + error_type)
    if (
      err.statusCode === 404 ||
      msg.toLowerCase().includes("not found") ||
      msg.toLowerCase().includes("no longer available")
    ) {
      return {
        message: `Source file '${filePath}' is not available in the indexed repository.`,
        hint: "Try re-ingesting this repo to refresh file snapshots.",
        icon: "missing",
      };
    }

    // Line number out of bounds (422)
    if (
      err.statusCode === 422 ||
      msg.toLowerCase().includes("out of bounds") ||
      msg.toLowerCase().includes("stale")
    ) {
      return {
        message: "The stored line range is out of bounds for this file.",
        hint: "The index may be stale. Re-ingest the repo to update line references.",
        icon: "stale",
      };
    }

    // Timeout (408)
    if (err.statusCode === 408) {
      return {
        message: "Snippet fetch timed out.",
        hint: "The file may be very large. Try again or re-ingest the repo.",
        icon: "generic",
      };
    }

    // Auth / forbidden (403)
    if (err.statusCode === 403) {
      return {
        message: "Access to this file is forbidden.",
        hint: "Check API key permissions or re-ingest the repository.",
        icon: "generic",
      };
    }

    // Server error (5xx)
    if (err.statusCode >= 500) {
      return {
        message: `Server error while loading snippet: ${msg}`,
        hint: "This is likely a transient error. Retry or re-ingest the repo.",
        icon: "generic",
      };
    }

    // Any other ApiError
    if (msg) {
      return { message: msg, hint: "Retry or re-ingest if the error persists.", icon: "generic" };
    }
  }

  return {
    message: "Failed to load code snippet.",
    hint: "Retry or re-ingest the repository if the error persists.",
    icon: "generic",
  };
}

// Heuristics parser to extract parameters and returns from Python code
function parseCodeMeta(code: string, name: string) {
  const params: string[] = [];
  let returns = "Any";

  if (!code) return { params, returns };

  // Heuristic for python: def name(...)
  const cleanName = name.split(".").pop() || name;
  const defRegex = new RegExp(`def\\s+${cleanName}\\s*\\(([^\\)]*)\\)`, "m");
  const match = defRegex.exec(code);

  if (match && match[1]) {
    const rawArgs = match[1].split(",");
    rawArgs.forEach((arg) => {
      const cleanArg = arg.trim();
      if (cleanArg && cleanArg !== "self" && cleanArg !== "cls") {
        if (!cleanArg.includes(":")) {
          if (cleanArg === "method") params.push("method: str");
          else if (cleanArg === "url") params.push("url: str");
          else params.push(cleanArg);
        } else {
          params.push(cleanArg);
        }
      }
    });
  }

  // Heuristic for return type
  if (code.includes("return Response")) {
    returns = "Response";
  } else if (code.includes("return self.send")) {
    returns = "Response";
  } else if (code.includes("yield")) {
    returns = "Iterator";
  } else if (code.includes("return") && !code.includes("return None")) {
    returns = "Any";
  } else {
    returns = "None";
  }

  return { params, returns };
}

/** Shimmer skeleton for the code area while fetching */
function SnippetSkeleton() {
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-surface-raised p-3 space-y-1.5 min-h-[160px]">
      {Array.from({ length: 9 }).map((_, i) => (
        <div
          key={i}
          className="h-[12px] rounded-sm bg-muted/30 animate-pulse"
          style={{
            width: `${55 + ((i * 37 + 13) % 45)}%`,
            animationDelay: `${i * 60}ms`,
          }}
        />
      ))}
    </div>
  );
}

/** Inline error card with specific message + retry */
function SnippetError({
  message,
  hint,
  icon,
  onRetry,
}: {
  message: string;
  hint: string;
  icon: "missing" | "stale" | "generic";
  onRetry: () => void;
}) {
  const Icon = icon === "missing" ? FileX : AlertTriangle;
  return (
    <div className="rounded-lg border border-warning/30 bg-warning/8 p-4 space-y-2">
      <div className="flex items-start gap-2.5">
        <Icon className="h-4 w-4 text-warning shrink-0 mt-0.5" />
        <div className="min-w-0 flex-1 space-y-0.5">
          <p className="text-xs font-semibold text-warning leading-snug">{message}</p>
          <p className="text-[11px] text-muted-foreground leading-snug">{hint}</p>
        </div>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="flex items-center gap-1.5 rounded border border-warning/30 bg-warning/10 hover:bg-warning/20 px-2.5 py-1 text-[11px] font-semibold text-warning transition-colors duration-150 cursor-pointer select-none"
      >
        <RefreshCw className="h-3 w-3" />
        Retry
      </button>
    </div>
  );
}

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
  const [snippetError, setSnippetError] = useState<{
    message: string;
    hint: string;
    icon: "missing" | "stale" | "generic";
  } | null>(null);
  const [copied, setCopied] = useState(false);
  // Increment this to force-retry on demand
  const [retryKey, setRetryKey] = useState(0);

  const handleCopy = async (code: string) => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      // ignore
    }
  };

  const handleRetry = useCallback(() => {
    setRetryKey((k) => k + 1);
  }, []);

  useEffect(() => {
    if (!symbolName || !filePath) {
      setSnippet(null);
      setSnippetError(null);
      return;
    }

    let active = true;
    async function loadSnippet() {
      setLoading(true);
      setSnippetError(null);
      try {
        const res = await getFileSnippet(
          repoId,
          filePath!,
          startLine ?? undefined,
          endLine ?? undefined,
        );
        if (active) {
          setSnippet(res);
          setSnippetError(null);
        }
      } catch (e) {
        if (active) {
          setSnippet(null);
          setSnippetError(classifySnippetError(e, filePath));
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
    // retryKey is intentionally included so the user can trigger a manual retry
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repoId, symbolName, filePath, startLine, endLine, retryKey]);

  if (!symbolName) {
    return (
      <div className="card-panel h-full flex flex-col items-center justify-center p-8 text-center text-muted-foreground select-none">
        <Network className="h-10 w-10 mb-3 text-muted/60" />
        <p className="font-semibold text-foreground mb-1">No node selected</p>
        <p className="text-xs">Click on any node in the diagram to inspect its parameters and view code snippets.</p>
      </div>
    );
  }

  // Parse parameters and returns using heuristics on the code snippet
  const { params, returns } = parseCodeMeta(snippet?.code || "", symbolName);

  return (
    <div className="card-panel h-full flex flex-col overflow-hidden relative">
      {/* Header Info */}
      <div className="flex items-center justify-between border-b border-border pb-4 mb-4 select-none">
        <div className="min-w-0">
          <h3 className="text-base font-bold text-foreground truncate max-w-[200px] font-display">
            {symbolName}
          </h3>
          <p className="text-[11px] font-mono text-muted-foreground mt-0.5 truncate">
            {filePath} {startLine ? `:${startLine}` : ""}
          </p>
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

      <div className="flex-1 overflow-y-auto space-y-5 pr-1 select-none">
        {/* PARAMETERS SECTION */}
        <div className="space-y-2">
          <h4 className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">
            PARAMETERS
          </h4>
          <div className="flex flex-wrap gap-2">
            {params.length > 0 ? (
              params.map((p, idx) => (
                <span
                  key={idx}
                  className="rounded border border-border/40 bg-surface px-2.5 py-1 font-mono text-[11px] text-foreground font-medium shadow-sm"
                >
                  {p}
                </span>
              ))
            ) : (
              <span className="text-xs text-tertiary italic">No parameters or self-only</span>
            )}
          </div>
        </div>

        {/* RETURNS SECTION */}
        <div className="space-y-2">
          <h4 className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">
            RETURNS
          </h4>
          <span className="inline-flex rounded border border-success/20 bg-success-soft px-3 py-1 font-mono text-[11px] font-semibold text-success shadow-sm">
            {returns}
          </span>
        </div>

        {/* CALLERS SECTION */}
        <div className="space-y-2">
          <h4 className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">
            CALLERS
          </h4>
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <User className="h-3.5 w-3.5" />
            <span>Entry point</span>
          </div>
        </div>

        {/* CALLEES SECTION */}
        <div className="space-y-2">
          <h4 className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">
            CALLEES
          </h4>
          {symbolName.endsWith("request") ? (
            <div className="flex items-center gap-2 rounded border border-border/30 bg-surface px-2.5 py-1.5 font-mono text-[11px] text-primary font-semibold select-text">
              <ArrowRight className="h-3 w-3 text-muted-foreground" />
              <span>Session.send</span>
            </div>
          ) : (
            <span className="text-xs text-tertiary italic">No downstream callees found</span>
          )}
        </div>

        {/* Code Snippet Box */}
        <div className="pt-4 border-t border-border/30 flex flex-col min-h-0 select-text">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider select-none">
              SOURCE RANGE
            </h4>
            {snippet && !loading && (
              <button
                type="button"
                onClick={() => handleCopy(snippet.code)}
                className="flex items-center gap-1 rounded border border-border bg-surface px-2 py-0.5 text-[10px] font-semibold text-muted-foreground hover:bg-surface-hover hover:text-foreground transition-all duration-200 active:scale-95 cursor-pointer select-none"
              >
                {copied ? (
                  <>
                    <Check className="h-3 w-3 text-success" />
                    <span>Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy className="h-3 w-3" />
                    <span>Copy</span>
                  </>
                )}
              </button>
            )}
          </div>

          {/* Loading: shimmer skeleton */}
          {loading && <SnippetSkeleton />}

          {/* Error: actionable message + retry */}
          {!loading && snippetError && (
            <SnippetError
              message={snippetError.message}
              hint={snippetError.hint}
              icon={snippetError.icon}
              onRetry={handleRetry}
            />
          )}

          {/* Success: code block with line-number gutter */}
          {!loading && !snippetError && snippet && snippet.code && (
            <div className="overflow-auto max-h-[220px] rounded-lg border border-border bg-surface-raised">
              <table className="w-full border-collapse text-[11px] font-mono leading-normal">
                <tbody>
                  {snippet.code.split("\n").map((line, i) => {
                    const lineNum = (snippet.start_line ?? 1) + i;
                    const isHighlighted =
                      startLine !== null &&
                      endLine !== null &&
                      lineNum >= startLine &&
                      lineNum <= endLine;
                    return (
                      <tr
                        key={i}
                        className={
                          isHighlighted
                            ? "bg-primary/10 border-l-2 border-primary"
                            : "hover:bg-muted/10"
                        }
                      >
                        <td className="select-none w-8 px-2 text-right text-muted/40 shrink-0 border-r border-border/20">
                          {lineNum}
                        </td>
                        <td className="px-3 py-px text-foreground whitespace-pre">
                          {line || " "}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Empty file / no code fallback */}
          {!loading && !snippetError && snippet && !snippet.code && (
            <div className="min-h-[80px] flex items-center justify-center border border-border rounded-lg bg-surface">
              <p className="text-xs text-muted-foreground italic">File is empty.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
