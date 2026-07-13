"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import type { ChatMessage } from "@/lib/types";

const REPO_KEY = "cn_repo_id";
const REPO_CHANGE = "cn-repo-change";

type AppContextValue = {
  repoId: string | null;
  setRepoId: (id: string | null) => void;
  sessionId: string;
  resetSession: () => void;
  chatHistory: ChatMessage[];
  setChatHistory: React.Dispatch<React.SetStateAction<ChatMessage[]>>;
  lastDiagramSymbol: string | null;
  setLastDiagramSymbol: (s: string | null) => void;
  clearSession: () => void;
};

const AppContext = createContext<AppContextValue | null>(null);

function newSessionId(): string {
  return crypto.randomUUID();
}

function readRepoFromStorage(): string | null {
  try {
    return localStorage.getItem(REPO_KEY);
  } catch {
    return null;
  }
}

function subscribeRepo(onChange: () => void) {
  if (typeof window === "undefined") return () => undefined;
  const handler = () => onChange();
  window.addEventListener(REPO_CHANGE, handler);
  window.addEventListener("storage", handler);
  return () => {
    window.removeEventListener(REPO_CHANGE, handler);
    window.removeEventListener("storage", handler);
  };
}

export function AppProvider({ children }: { children: ReactNode }) {
  const repoId = useSyncExternalStore(
    subscribeRepo,
    readRepoFromStorage,
    () => null,
  );

  const [sessionId, setSessionId] = useState(newSessionId);
  const [chatByRepo, setChatByRepo] = useState<Record<string, ChatMessage[]>>(
    {},
  );
  const [lastDiagramByRepo, setLastDiagramByRepo] = useState<
    Record<string, string | null>
  >({});

  const chatHistory = useMemo(
    () => (repoId ? (chatByRepo[repoId] ?? []) : []),
    [repoId, chatByRepo],
  );
  const lastDiagramSymbol = useMemo(
    () => (repoId ? (lastDiagramByRepo[repoId] ?? null) : null),
    [repoId, lastDiagramByRepo],
  );

  const prevRepoRef = useRef<string | null>(readRepoFromStorage());

  const setRepoId = useCallback((id: string | null) => {
    const prev = prevRepoRef.current;
    try {
      if (id) localStorage.setItem(REPO_KEY, id);
      else localStorage.removeItem(REPO_KEY);
    } catch {
      /* ignore */
    }
    if (id && prev && id !== prev) {
      setSessionId(newSessionId());
    }
    prevRepoRef.current = id;
    window.dispatchEvent(new Event(REPO_CHANGE));
  }, []);

  const setChatHistory = useCallback(
    (action: React.SetStateAction<ChatMessage[]>) => {
      if (!repoId) return;
      setChatByRepo((prev) => {
        const current = prev[repoId] ?? [];
        const next = typeof action === "function" ? action(current) : action;
        return { ...prev, [repoId]: next };
      });
    },
    [repoId],
  );

  const setLastDiagramSymbol = useCallback(
    (symbol: string | null) => {
      if (!repoId) return;
      setLastDiagramByRepo((prev) => ({ ...prev, [repoId]: symbol }));
    },
    [repoId],
  );

  const resetSession = useCallback(() => {
    setSessionId(newSessionId());
  }, []);

  const clearSession = useCallback(() => {
    setRepoId(null);
    setChatByRepo({});
    setLastDiagramByRepo({});
    setSessionId(newSessionId());
  }, [setRepoId]);

  const value = useMemo(
    () => ({
      repoId,
      setRepoId,
      sessionId,
      resetSession,
      chatHistory,
      setChatHistory,
      lastDiagramSymbol,
      setLastDiagramSymbol,
      clearSession,
    }),
    [
      repoId,
      setRepoId,
      sessionId,
      resetSession,
      chatHistory,
      setChatHistory,
      lastDiagramSymbol,
      setLastDiagramSymbol,
      clearSession,
    ],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within AppProvider");
  return ctx;
}
