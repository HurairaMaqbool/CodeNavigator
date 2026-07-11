"use client";

import { memo } from "react";
import { ShieldAlert, Zap } from "lucide-react";
import type { ChatMessage } from "@/lib/types";
import { cn } from "@/lib/utils";
import { CitationChip } from "./citation-chip";

export const ChatMessageBubble = memo(function ChatMessageBubble({
  message,
}: {
  message: ChatMessage;
}) {
  const isUser = message.role === "user";

  return (
    <div
      className={cn("flex w-full", isUser ? "justify-end" : "justify-start")}
    >
      <div
        className={cn(
          "max-w-[90%] rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm",
          isUser
            ? "bg-primary text-primary-foreground"
            : "border border-border bg-surface text-foreground",
        )}
      >
        {message.gated && !isUser && (
          <div className="mb-2 flex items-center gap-2 text-warning">
            <ShieldAlert className="h-4 w-4 shrink-0" aria-hidden />
            <span className="text-xs font-medium">Gated response</span>
          </div>
        )}
        <div className="whitespace-pre-wrap">{message.content}</div>
        {!isUser && message.cache_hit && (
          <p className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
            <Zap className="h-3 w-3" aria-hidden />
            Cache hit
          </p>
        )}
        {!isUser && message.sources && message.sources.length > 0 && (
          <details className="mt-3">
            <summary className="cursor-pointer text-xs font-medium text-muted-foreground">
              Sources ({message.sources.length})
            </summary>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {message.sources.map((s, i) => (
                <CitationChip key={`${s.file_path}-${i}`} source={s} />
              ))}
            </div>
          </details>
        )}
        {!isUser && message.trace && message.trace.length > 0 && (
          <details className="mt-2">
            <summary className="cursor-pointer text-xs font-medium text-muted-foreground">
              Agent trace
            </summary>
            <pre className="mt-2 max-h-40 overflow-auto rounded bg-muted/50 p-2 font-mono text-xs">
              {JSON.stringify(message.trace, null, 2)}
            </pre>
          </details>
        )}
        {message.elapsed_s != null && !isUser && (
          <p className="mt-2 text-xs text-muted-foreground">
            Completed in {message.elapsed_s.toFixed(1)}s
          </p>
        )}
      </div>
    </div>
  );
});
