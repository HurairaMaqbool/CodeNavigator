"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, Send } from "lucide-react";
import { toast } from "sonner";
import {
  chatWithRetry,
  createChatRequestGuard,
  openChatStream,
} from "@/lib/api";
import { CHAT_STARTER_PROMPTS } from "@/lib/constants";
import { notifyChatQuerySuccess } from "@/lib/chat-query-events";
import { useApp } from "@/lib/context/app-context";
import { ApiError, type ChatMessage } from "@/lib/types";
import { EmptyState } from "@/components/shared/empty-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AgentStepIndicator } from "./agent-step-indicator";
import { ChatMessageBubble } from "./chat-message";
import { VoiceInputButton } from "./voice-input-button";

type ChatPanelProps = {
  repoId: string;
  ready: boolean;
};

function chatErrorContent(
  e: unknown,
  question: string,
): Pick<ChatMessage, "content" | "gated" | "retry_question"> {
  if (e instanceof ApiError) {
    if (e.statusCode === 409) {
      return {
        content: "This repository is still indexing. Give it a moment, then try again.",
        gated: true,
        retry_question: question,
      };
    }
    if (e.statusCode === 429) {
      return {
        content: e.retryAfterS
          ? `The AI provider is busy. Wait about ${e.retryAfterS} seconds, then retry.`
          : "The AI provider is temporarily busy. Please try again shortly.",
        gated: true,
        retry_question: question,
      };
    }
    if (e.statusCode === 408 || e.statusCode === 504) {
      return {
        content:
          "This question took too long to complete. Try a narrower, more specific question.",
        gated: true,
        retry_question: question,
      };
    }
    return { content: e.message, gated: true, retry_question: question };
  }
  return {
    content: "Something went wrong while processing your question.",
    gated: true,
    retry_question: question,
  };
}

export function ChatPanel({ repoId, ready }: ChatPanelProps) {
  const { sessionId, chatHistory, setChatHistory } = useApp();
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [agentState, setAgentState] = useState<string | null>(null);
  const closeStreamRef = useRef<(() => void) | null>(null);
  const requestGuardRef = useRef<ReturnType<typeof createChatRequestGuard> | null>(
    null,
  );
  const inFlightRef = useRef(false);

  useEffect(() => {
    return () => {
      closeStreamRef.current?.();
      closeStreamRef.current = null;
      requestGuardRef.current?.dispose(true);
      requestGuardRef.current = null;
    };
  }, []);

  const sendQuestion = useCallback(
    async (q: string) => {
      const trimmed = q.trim();
      if (!trimmed || !ready || inFlightRef.current) return;

      inFlightRef.current = true;
      const userMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "user",
        content: trimmed,
      };
      setChatHistory((h) => [...h, userMsg]);
      setQuestion("");
      setLoading(true);
      setAgentState("INTAKE");

      const t0 = performance.now();
      closeStreamRef.current?.();
      closeStreamRef.current = null;
      requestGuardRef.current?.dispose(false);
      const guard = createChatRequestGuard();
      requestGuardRef.current = guard;

      closeStreamRef.current = openChatStream(
        sessionId,
        (state) => setAgentState(state),
        () => {},
        () => guard.bump(),
      );

      try {
        const res = await chatWithRetry(
          { repo_id: repoId, question: trimmed, session_id: sessionId },
          guard,
        );
        const elapsed = (performance.now() - t0) / 1000;
        setChatHistory((h) => [
          ...h,
          {
            id: crypto.randomUUID(),
            role: "assistant",
            content: res.answer,
            gated: res.gated || Boolean(res.timed_out),
            cache_hit: res.cache_hit,
            sources: res.sources,
            trace: res.trace,
            confidence_score: res.confidence_score,
            elapsed_s: elapsed,
          },
        ]);
        notifyChatQuerySuccess(repoId);
        setAgentState("RESPOND");
      } catch (e) {
        const errMsg = chatErrorContent(e, trimmed);
        setChatHistory((h) => [
          ...h,
          { id: crypto.randomUUID(), role: "assistant", ...errMsg },
        ]);
        toast.error("Message couldn't be sent");
      } finally {
        guard.dispose(false);
        if (requestGuardRef.current === guard) requestGuardRef.current = null;
        closeStreamRef.current?.();
        closeStreamRef.current = null;
        inFlightRef.current = false;
        setLoading(false);
        setTimeout(() => setAgentState(null), 1800);
      }
    },
    [repoId, ready, sessionId, setChatHistory],
  );

  return (
    <div className="card-surface flex h-full min-h-[520px] flex-col overflow-hidden shadow-elev-1">
      {loading && agentState && (
        <div className="border-b border-border px-5 py-3">
          <AgentStepIndicator currentState={agentState} />
        </div>
      )}

      <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5">
        {chatHistory.length === 0 ? (
          <EmptyState
            title="Ask your codebase anything"
            description="Architecture, symbols, call flows — answers include file citations you can verify."
            action={
              <div className="flex flex-wrap justify-center gap-2">
                {CHAT_STARTER_PROMPTS.map((p) => (
                  <button
                    key={p}
                    type="button"
                    disabled={!ready}
                    onClick={() => void sendQuestion(p)}
                    className="prompt-chip"
                  >
                    {p}
                  </button>
                ))}
              </div>
            }
          />
        ) : (
          chatHistory.map((m) => (
            <ChatMessageBubble
              key={m.id}
              message={m}
              onRetry={
                m.retry_question && !loading
                  ? () => void sendQuestion(m.retry_question!)
                  : undefined
              }
            />
          ))
        )}
        {loading && (
          <div className="flex flex-col gap-2 rounded-2xl border border-primary/25 bg-surface p-4 shadow-elev-2 max-w-sm animate-cascade">
            <div className="flex items-center gap-2">
              {/* Custom animated bouncing dots simulating directory search */}
              <div className="flex items-center gap-1.5 h-6">
                <span className="w-1.5 h-1.5 rounded-full bg-primary animate-bounce" style={{ animationDelay: "0ms" }} />
                <span className="w-1.5 h-1.5 rounded-full bg-primary animate-bounce" style={{ animationDelay: "150ms" }} />
                <span className="w-1.5 h-1.5 rounded-full bg-primary animate-bounce" style={{ animationDelay: "300ms" }} />
              </div>
              <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                Agent reasoning
              </span>
            </div>
            
            <div className="flex items-start gap-2.5 mt-1">
              <svg className="h-4 w-4 text-primary shrink-0 mt-0.5 animate-pulse" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
                <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
                <line x1="12" y1="22.08" x2="12" y2="12" />
              </svg>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-mono text-foreground font-medium truncate">
                  {agentState === "ACT"
                    ? "Searching semantic dense index..."
                    : agentState === "FINALIZE"
                      ? "Synthesizing retrieved context chunks..."
                      : "Scanning symbol graph for references..."}
                </p>
                <p className="text-[10px] text-muted-foreground font-mono mt-0.5">
                  status: {agentState || "INITIALIZING"}
                </p>
              </div>
            </div>
          </div>
        )}
      </div>

      <form
        className="shrink-0 px-6 py-4 border-t border-border/40 bg-background w-full"
        onSubmit={(e) => {
          e.preventDefault();
          if (question.trim()) {
            void sendQuestion(question);
          }
        }}
      >
        <div className="max-w-5xl mx-auto">
          <div className="relative rounded-2xl border border-border bg-surface focus-within:border-primary/40 focus-within:ring-2 focus-within:ring-ring transition-all duration-200 shadow-sm">
            <textarea
              rows={1}
              placeholder={
                ready ? "Ask about architecture, classes, or flows…" : "Waiting for index to finish…"
              }
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  if (question.trim()) {
                    void sendQuestion(question);
                  }
                }
              }}
              disabled={!ready || loading}
              aria-label="Chat message"
              className="w-full bg-transparent resize-none px-5 py-4 pr-32 text-sm text-foreground placeholder:text-muted-foreground/60 focus:outline-none min-h-[52px]"
            />
            
            {/* Right Cluster Controls */}
            <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1.5 z-10 select-none">
              <VoiceInputButton
                onTranscript={(text) => setQuestion(text)}
                disabled={!ready || loading}
              />
              <button
                type="submit"
                disabled={!ready || loading || !question.trim()}
                aria-label="Send message"
                className="grid size-9 place-items-center rounded-lg bg-primary text-primary-foreground disabled:opacity-40 disabled:hover:brightness-100 hover:brightness-110 glow-primary active:scale-95 transition-all duration-200 cursor-pointer"
              >
                {loading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </button>
            </div>
          </div>

          <p className="text-[11px] text-muted-foreground mt-2 ml-2 select-none">
            Enter to send &middot; Shift+Enter for newline
          </p>
        </div>
      </form>
    </div>
  );
}
