"use client";

import { memo } from "react";
import { RotateCcw, ShieldAlert } from "lucide-react";
import type { ChatMessage } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { CitationChip } from "./citation-chip";

export const ChatMessageBubble = memo(function ChatMessageBubble({
  message,
  onRetry,
}: {
  message: ChatMessage;
  onRetry?: () => void;
}) {
  const isUser = message.role === "user";

  return (
    <div
      className={cn("flex w-full", isUser ? "justify-end" : "justify-start")}
    >
      <article
        className={cn(
          "max-w-[90%] px-5 py-4 text-sm leading-relaxed",
          isUser
            ? "border border-border bg-surface-raised/70 text-foreground rounded-2xl rounded-tr-sm"
            : "border border-border bg-surface/40 text-foreground rounded-2xl rounded-tl-sm shadow-elev-1",
        )}
      >
        {message.gated && !isUser && (
          <div className="mb-3 flex items-center gap-2 text-warning">
            <ShieldAlert className="h-3.5 w-3.5 shrink-0" aria-hidden />
            <span className="text-xs font-semibold">Low confidence — review sources</span>
          </div>
        )}
        <div className="whitespace-pre-wrap text-[14px] leading-relaxed text-foreground/95">
          {message.content}
        </div>

        {onRetry && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mt-4 active:scale-[0.98]"
            onClick={onRetry}
          >
            <RotateCcw className="h-3.5 w-3.5" />
            Retry question
          </Button>
        )}

        {!isUser && message.sources && message.sources.length > 0 && (
          <div className="mt-4 border-t border-border/40 pt-3">
            <p className="micro-label mb-2 text-tertiary select-none">Cited files</p>
            <div className="flex flex-wrap gap-1.5">
              {message.sources.map((s, i) => (
                <CitationChip key={`${s.file_path}-${i}`} source={s} />
              ))}
            </div>
          </div>
        )}

        {!isUser && (
          <footer className="mt-3.5 flex flex-wrap items-center gap-3.5 text-xs text-tertiary select-none">
            {message.cache_hit && <span className="bg-primary/10 text-primary px-1.5 py-0.5 rounded text-[10px] font-semibold tracking-wide">Cached</span>}
            {message.confidence_score != null && (
              <span className="flex items-center gap-1.5">
                <span
                  className={cn(
                    "h-1.5 w-1.5 rounded-full",
                    message.gated ? "bg-warning" : "bg-success",
                  )}
                  aria-hidden
                />
                Confidence {message.confidence_score.toFixed(1)}
              </span>
            )}
            {message.elapsed_s != null && (
              <span>{message.elapsed_s.toFixed(1)}s</span>
            )}
          </footer>
        )}

        {!isUser && message.trace && message.trace.length > 0 && (
          <details className="mt-3 border-t border-border/30 pt-2">
            <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground select-none">
              Agent trace
            </summary>
            <pre className="mt-2 max-h-36 overflow-auto rounded-md border border-border bg-background p-3 font-mono text-[11px] text-muted-foreground">
              {JSON.stringify(message.trace, null, 2)}
            </pre>
          </details>
        )}
      </article>
    </div>
  );
});
