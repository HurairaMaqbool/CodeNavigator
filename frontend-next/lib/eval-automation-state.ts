/** Per-repo automation locks, debounce, and dedupe keys (sessionStorage). */

export const INDEX_DEBOUNCE_MS = 45_000;
export const QUERY_REFRESH_DEBOUNCE_MS = 30_000;
export const QUERY_RAGAS_DEBOUNCE_MS = 60_000;
export const CHAT_QUERY_RAGAS_THRESHOLD = 10;

export const CHAT_QUERY_SUCCESS_EVENT = "cn-chat-query-success";

type Op = "ragas" | "golden" | "compare";

const locks = new Map<string, Set<Op>>();
const debounceTimers = new Map<string, ReturnType<typeof setTimeout>>();

function storageKey(repoId: string, suffix: string): string {
  return `cn_eval_${suffix}_${repoId}`;
}

export function tryAcquireEvalLock(repoId: string, op: Op): boolean {
  const set = locks.get(repoId) ?? new Set<Op>();
  if (set.has(op)) return false;
  set.add(op);
  locks.set(repoId, set);
  return true;
}

export function releaseEvalLock(repoId: string, op: Op): void {
  locks.get(repoId)?.delete(op);
}

export function isEvalLocked(repoId: string, op: Op): boolean {
  return locks.get(repoId)?.has(op) ?? false;
}

export function clearEvalLocks(repoId?: string): void {
  if (repoId) locks.delete(repoId);
  else locks.clear();
}

export function scheduleDebounced(
  debounceKey: string,
  fn: () => void,
  delayMs: number,
): void {
  const existing = debounceTimers.get(debounceKey);
  if (existing) clearTimeout(existing);
  const timer = setTimeout(() => {
    debounceTimers.delete(debounceKey);
    fn();
  }, delayMs);
  debounceTimers.set(debounceKey, timer);
}

export function cancelDebounced(debounceKey: string): void {
  const t = debounceTimers.get(debounceKey);
  if (t) clearTimeout(t);
  debounceTimers.delete(debounceKey);
}

export function scheduleIndexDebounced(
  repoId: string,
  fn: () => void,
  delayMs = INDEX_DEBOUNCE_MS,
): void {
  scheduleDebounced(`index:${repoId}`, fn, delayMs);
}

export function scheduleQueryRefreshDebounced(
  repoId: string,
  fn: () => void,
  delayMs = QUERY_REFRESH_DEBOUNCE_MS,
): void {
  scheduleDebounced(`query_refresh:${repoId}`, fn, delayMs);
}

export function scheduleQueryRagasDebounced(
  repoId: string,
  fn: () => void,
  delayMs = QUERY_RAGAS_DEBOUNCE_MS,
): void {
  scheduleDebounced(`query_ragas:${repoId}`, fn, delayMs);
}

export function readLastAutoIndexCommit(repoId: string): string | null {
  try {
    return sessionStorage.getItem(storageKey(repoId, "last_index_commit"));
  } catch {
    return null;
  }
}

export function writeLastAutoIndexCommit(
  repoId: string,
  commitHash: string,
): void {
  try {
    sessionStorage.setItem(storageKey(repoId, "last_index_commit"), commitHash);
  } catch {
    /* ignore */
  }
}

export function readLastAutoComparePair(repoId: string): string | null {
  try {
    return sessionStorage.getItem(storageKey(repoId, "last_compare_pair"));
  } catch {
    return null;
  }
}

export function writeLastAutoComparePair(
  repoId: string,
  pairKey: string,
): void {
  try {
    sessionStorage.setItem(storageKey(repoId, "last_compare_pair"), pairKey);
  } catch {
    /* ignore */
  }
}

export function readChatQueryCount(repoId: string): number {
  try {
    const raw = sessionStorage.getItem(storageKey(repoId, "chat_query_count"));
    if (!raw) return 0;
    const n = Number.parseInt(raw, 10);
    return Number.isFinite(n) && n >= 0 ? n : 0;
  } catch {
    return 0;
  }
}

export function writeChatQueryCount(repoId: string, count: number): void {
  try {
    sessionStorage.setItem(
      storageKey(repoId, "chat_query_count"),
      String(Math.max(0, count)),
    );
  } catch {
    /* ignore */
  }
}

/** Increment successful chat query count; returns new total. */
export function incrementChatQueryCount(repoId: string): number {
  const next = readChatQueryCount(repoId) + 1;
  writeChatQueryCount(repoId, next);
  return next;
}

export function shouldTriggerQueryRagas(count: number): boolean {
  return (
    count >= CHAT_QUERY_RAGAS_THRESHOLD &&
    count % CHAT_QUERY_RAGAS_THRESHOLD === 0
  );
}

export function logEvalAutomation(
  event: string,
  detail: Record<string, unknown>,
): void {
  if (process.env.NODE_ENV === "development") {
    console.info("[eval-automation]", event, detail);
  }
}
