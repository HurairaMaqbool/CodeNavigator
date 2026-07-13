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
          <div className="flex items-center gap-2.5 rounded-xl border border-primary/15 bg-primary-tint/30 px-4 py-3 text-xs font-semibold text-primary animate-pulse w-fit">
            <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
            <span>
              {agentState === "ACT"
                ? "Searching dense & sparse index..."
                : agentState === "FINALIZE"
                  ? "Formulating final response..."
                  : "Processing query through state loop..."}
            </span>
          </div>
        )}
      </div>

      <form
        className="relative flex flex-col gap-2 border-t border-border bg-surface-raised/40 p-4 backdrop-blur-md"
        onSubmit={(e) => {
          e.preventDefault();
          void sendQuestion(question);
        }}
      >
        <div className="relative flex items-center">
          <Input
            placeholder={
              ready ? "Ask about architecture, classes, or flows…" : "Waiting for index to finish…"
            }
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            disabled={!ready || loading}
            aria-label="Chat message"
            className="flex-1 bg-surface/30 border-border hover:border-border-strong focus:border-primary pr-32 transition-colors min-h-[44px] rounded-xl pl-4"
          />
          <div className="absolute right-2 flex items-center gap-1.5">
            <VoiceInputButton
              onTranscript={(text) => setQuestion(text)}
              disabled={!ready || loading}
            />
            {ready && !loading && (
              <kbd className="hidden h-5 select-none items-center gap-0.5 rounded border border-border bg-surface px-1.5 font-mono text-[10px] font-medium text-tertiary sm:flex">
                <span>Enter</span>
              </kbd>
            )}
            <Button
              type="submit"
              size="sm"
              disabled={!ready || loading || !question.trim()}
              aria-label="Send message"
              className="rounded-lg h-8 px-3 flex items-center gap-1 font-semibold active:scale-[0.98]"
            >
              {loading ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Send className="h-3.5 w-3.5" />
              )}
              <span>Ask</span>
            </Button>
          </div>
        </div>
      </form>
    </div>
  );
}
