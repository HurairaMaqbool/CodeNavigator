export const BRAND = {
  name: "CodeNavigator",
  tagline: "Understand any codebase in minutes",
  version: "1.0.0",
} as const;

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ??
  "http://127.0.0.1:8000";

export const API_KEY = process.env.NEXT_PUBLIC_API_KEY ?? "";

export const QUICK_START_REPOS = [
  {
    label: "psf / requests",
    url: "https://github.com/psf/requests",
    ref: "main",
  },
  {
    label: "pallets / flask",
    url: "https://github.com/pallets/flask",
    ref: "main",
  },
] as const;

export const INGEST_STEPS = [
  { key: "clone", label: "Clone" },
  { key: "filter", label: "Filter" },
  { key: "parse", label: "Parse" },
  { key: "chunk", label: "Chunk" },
  { key: "index", label: "Index" },
  { key: "synced", label: "Synced" },
] as const;

export const AGENT_STEPS = [
  "INTAKE",
  "PLAN",
  "ACT",
  "OBSERVE",
  "DECIDE",
  "FINALIZE",
  "VERIFY",
] as const;

export const AGENT_STEP_LABELS: Record<string, string> = {
  INTAKE: "Receive",
  PLAN: "Understand",
  ACT: "Search",
  OBSERVE: "Read",
  DECIDE: "Reason",
  FINALIZE: "Write",
  VERIFY: "Verify",
  RESPOND: "Done",
};

export const CHAT_STARTER_PROMPTS = [
  "How does Session.send work?",
  "Where is HTTPBasicAuth defined?",
  "The role of urllib3.PoolManager",
] as const;

/** Reset when SSE activity arrives; only abort if the stream goes silent. */
export const CHAT_IDLE_TIMEOUT_MS = 120_000;
/** Hard ceiling for one chat POST — active-but-slow requests are not cut early. */
export const CHAT_ABSOLUTE_MAX_MS = 300_000;

export function repoIsReady(meta: {
  ready?: boolean;
  status?: string;
}): boolean {
  return meta.ready === true || meta.status === "ready";
}

export function ingestStepIndex(syncStatus: string): number {
  if (syncStatus === "synced") return INGEST_STEPS.length;
  const mapping: Record<string, number> = {
    cloning: 0,
    filtering: 1,
    parsing: 2,
    indexing: 4,
  };
  if (syncStatus in mapping) return mapping[syncStatus] + 1;
  if (
    ["pending", "indexing", "parsing", "filtering", "cloning"].includes(
      syncStatus,
    )
  ) {
    return mapping[syncStatus] ?? 3;
  }
  return 0;
}
