import { describe, expect, it, vi } from "vitest";
import {
  clearEvalLocks,
  releaseEvalLock,
  tryAcquireEvalLock,
} from "@/lib/eval-automation-state";

describe("eval runner lock semantics (race-condition guard)", () => {
  it("double acquire on same op is rejected; release allows re-acquire", () => {
    clearEvalLocks();
    expect(tryAcquireEvalLock("repo-1", "ragas")).toBe(true);
    expect(tryAcquireEvalLock("repo-1", "ragas")).toBe(false);
    releaseEvalLock("repo-1", "ragas");
    expect(tryAcquireEvalLock("repo-1", "ragas")).toBe(true);
  });

  it("parallel repos do not block each other", () => {
    clearEvalLocks();
    expect(tryAcquireEvalLock("a", "compare")).toBe(true);
    expect(tryAcquireEvalLock("b", "compare")).toBe(true);
    expect(tryAcquireEvalLock("a", "compare")).toBe(false);
  });

  it("different ops on same repo can coexist", () => {
    clearEvalLocks();
    expect(tryAcquireEvalLock("r", "ragas")).toBe(true);
    expect(tryAcquireEvalLock("r", "compare")).toBe(true);
    expect(tryAcquireEvalLock("r", "golden")).toBe(true);
  });
});

describe("notifyChatQuerySuccess", () => {
  it("dispatches custom event without throwing", async () => {
    const { notifyChatQuerySuccess } = await import("@/lib/chat-query-events");
    const { CHAT_QUERY_SUCCESS_EVENT } = await import(
      "@/lib/eval-automation-state"
    );
    const handler = vi.fn();
    window.addEventListener(CHAT_QUERY_SUCCESS_EVENT, handler);
    notifyChatQuerySuccess("repo-z");
    expect(handler).toHaveBeenCalledTimes(1);
    window.removeEventListener(CHAT_QUERY_SUCCESS_EVENT, handler);
  });
});

describe("auto-refresh data updates", () => {
  it("refreshEvalCachesQuietly triggers query invalidation and refetching", async () => {
    const { refreshEvalCachesQuietly } = await import("@/lib/eval-data-refresh");
    const mockQc = {
      invalidateQueries: vi.fn(),
      refetchQueries: vi.fn(),
      setQueryData: vi.fn(),
    } as any;
    
    refreshEvalCachesQuietly("repo-test", mockQc, "test-refresh");
    
    expect(mockQc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ["evalHistory"] });
    expect(mockQc.refetchQueries).toHaveBeenCalledWith({ queryKey: ["evalHistory"] });
    expect(mockQc.setQueryData).toHaveBeenCalledWith(["evalAutoLastRefresh", "repo-test"], expect.any(Number));
  });
});
