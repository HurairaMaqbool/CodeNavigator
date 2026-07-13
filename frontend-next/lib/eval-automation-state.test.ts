import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  CHAT_QUERY_RAGAS_THRESHOLD,
  clearEvalLocks,
  incrementChatQueryCount,
  readChatQueryCount,
  scheduleDebounced,
  shouldTriggerQueryRagas,
  tryAcquireEvalLock,
  writeChatQueryCount,
} from "@/lib/eval-automation-state";

describe("eval-automation-state", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    clearEvalLocks();
    sessionStorage.clear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("tryAcquireEvalLock prevents double ragas run per repo", () => {
    expect(tryAcquireEvalLock("repo-a", "ragas")).toBe(true);
    expect(tryAcquireEvalLock("repo-a", "ragas")).toBe(false);
    expect(tryAcquireEvalLock("repo-b", "ragas")).toBe(true);
  });

  it("scheduleDebounced coalesces rapid calls into one execution", () => {
    const fn = vi.fn();
    scheduleDebounced("test", fn, 1000);
    scheduleDebounced("test", fn, 1000);
    scheduleDebounced("test", fn, 1000);
    expect(fn).not.toHaveBeenCalled();
    vi.advanceTimersByTime(999);
    expect(fn).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("incrementChatQueryCount persists per repo in sessionStorage", () => {
    expect(incrementChatQueryCount("r1")).toBe(1);
    expect(incrementChatQueryCount("r1")).toBe(2);
    expect(readChatQueryCount("r1")).toBe(2);
    expect(readChatQueryCount("r2")).toBe(0);
    writeChatQueryCount("r2", 5);
    expect(readChatQueryCount("r2")).toBe(5);
  });

  it("shouldTriggerQueryRagas fires only on threshold multiples", () => {
    for (let i = 1; i < CHAT_QUERY_RAGAS_THRESHOLD; i += 1) {
      expect(shouldTriggerQueryRagas(i)).toBe(false);
    }
    expect(shouldTriggerQueryRagas(CHAT_QUERY_RAGAS_THRESHOLD)).toBe(true);
    expect(shouldTriggerQueryRagas(CHAT_QUERY_RAGAS_THRESHOLD + 1)).toBe(
      false,
    );
    expect(shouldTriggerQueryRagas(CHAT_QUERY_RAGAS_THRESHOLD * 2)).toBe(
      true,
    );
  });

  it("10 rapid query increments trigger RAGAS threshold exactly once at 10", () => {
    const triggers: number[] = [];
    for (let i = 1; i <= 10; i += 1) {
      const count = incrementChatQueryCount("repo-x");
      if (shouldTriggerQueryRagas(count)) triggers.push(count);
    }
    expect(triggers).toEqual([10]);
  });
});
