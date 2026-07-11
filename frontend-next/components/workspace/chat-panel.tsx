"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, Send } from "lucide-react";
import { toast } from "sonner";
import { chat, openChatStream } from "@/lib/api";
import { CHAT_STARTER_PROMPTS } from "@/lib/constants";
import { useApp } from "@/lib/context/app-context";
import { ApiError, type ChatMessage } from "@/lib/types";
import { EmptyState } from "@/components/shared/empty-state";
import { SectionHeader } from "@/components/shared/section-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AgentStepIndicator } from "./agent-step-indicator";
import { ChatMessageBubble } from "./chat-message";

type ChatPanelProps = {
  repoId: string;
  ready: boolean;
};

export function ChatPanel({ repoId, ready }: ChatPanelProps) {
  const { sessionId, chatHistory, setChatHistory } = useApp();
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [agentState, setAgentState] = useState<string | null>(null);
  const closeStreamRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    return () => {
      closeStreamRef.current?.();
      closeStreamRef.current = null;
    };
  }, []);

  const sendQuestion = useCallback(
    async (q: string) => {
      const trimmed = q.trim();
      if (!trimmed || !ready) return;

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
      closeStreamRef.current = openChatStream(
        sessionId,
        (state) => setAgentState(state),
        () => {
          /* SSE optional — chat still works */
        },
      );

      try {
        const res = await chat({
          repo_id: repoId,
          question: trimmed,
          session_id: sessionId,
        });
        const elapsed = (performance.now() - t0) / 1000;
        const assistant: ChatMessage = {
          id: crypto.randomUUID(),
          role: "assistant",
          content: res.answer,
          gated: res.gated,
          cache_hit: res.cache_hit,
          sources: res.sources,
          trace: res.trace,
          confidence_score: res.confidence_score,
          elapsed_s: elapsed,
        };
        setChatHistory((h) => [...h, assistant]);
        setAgentState("RESPOND");
      } catch (e) {
        let content = "Something went wrong.";
        if (e instanceof ApiError) {
          if (e.statusCode === 409) {
            content = "Repository is still indexing — try again shortly.";
          } else if (e.statusCode === 429) {
            content = e.retryAfterS
              ? `Rate limited — wait ${e.retryAfterS}s and retry.`
              : "Rate limited — please wait and retry.";
          } else if (e.statusCode === 504) {
            content =
              "Request timed out — the backend may be under heavy load. Try a simpler question.";
          } else {
            content = e.message;
          }
        }
        setChatHistory((h) => [
          ...h,
          {
            id: crypto.randomUUID(),
            role: "assistant",
            content,
            gated: true,
          },
        ]);
        toast.error("Chat failed");
      } finally {
        closeStreamRef.current?.();
        closeStreamRef.current = null;
        setLoading(false);
        setTimeout(() => setAgentState(null), 2000);
      }
    },
    [repoId, ready, sessionId, setChatHistory],
  );

  return (
    <div className="flex h-full min-h-[480px] flex-col rounded-xl border border-border bg-surface shadow-sm">
      <div className="border-b border-border p-4">
        <SectionHeader title="Chat" caption="Ask about architecture, symbols, and flows" />
        {loading && agentState && (
          <div className="mt-3">
            <AgentStepIndicator currentState={agentState} />
          </div>
        )}
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {chatHistory.length === 0 ? (
          <EmptyState
            title="Start a conversation"
            description="Ask how a function works, where a class is defined, or how modules connect."
            action={
              <div className="flex flex-wrap justify-center gap-2">
                {CHAT_STARTER_PROMPTS.map((p) => (
                  <button
                    key={p}
                    type="button"
                    disabled={!ready}
                    onClick={() => void sendQuestion(p)}
                    className="rounded-full border border-border bg-muted/50 px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary hover:text-primary disabled:opacity-50"
                  >
                    {p}
                  </button>
                ))}
              </div>
            }
          />
        ) : (
          chatHistory.map((m) => <ChatMessageBubble key={m.id} message={m} />)
        )}
        {loading && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Thinking…
          </div>
        )}
      </div>

      <form
        className="flex gap-2 border-t border-border p-4"
        onSubmit={(e) => {
          e.preventDefault();
          void sendQuestion(question);
        }}
      >
        <Input
          placeholder={ready ? "Ask about architecture…" : "Wait for indexing to finish…"}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={!ready || loading}
          aria-label="Chat message"
          className="flex-1"
        />
        <Button type="submit" disabled={!ready || loading || !question.trim()} aria-label="Send">
          <Send className="h-4 w-4" />
        </Button>
      </form>
    </div>
  );
}
