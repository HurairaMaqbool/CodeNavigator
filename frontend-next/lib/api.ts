import { API_BASE_URL, API_KEY } from "./constants";
import type {
  AuditEvent,
  ChatRequest,
  ChatResponse,
  CompareResult,
  DiagramResponse,
  EvalHealthResponse,
  EvalJobStatus,
  EvalRun,
  GoldenStatus,
  HealthResponse,
  IngestResponse,
  IngestStatusResponse,
  SubscriptionStatus,
  UsageSummary,
} from "./types";
import { ApiError } from "./types";

function headers(): HeadersInit {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (API_KEY) h["X-API-Key"] = API_KEY;
  return h;
}

function fetchWithTimeout(
  url: string,
  init: RequestInit,
  timeoutMs: number,
): Promise<Response> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  return fetch(url, { ...init, signal: ctrl.signal }).finally(() =>
    clearTimeout(timer),
  );
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (res.ok) {
    const text = await res.text();
    if (!text) return {} as T;
    try {
      return JSON.parse(text) as T;
    } catch {
      return { raw: text } as T;
    }
  }

  let msg = res.statusText;
  let retryAfterS: number | null = null;
  try {
    const err = (await res.json()) as {
      detail?: string | { message?: string; errors?: string[] };
      error?: string | object;
      message?: string;
    };
    const d = err.detail;
    if (typeof d === "string") {
      msg = d;
    } else if (d && typeof d === "object") {
      if ("message" in d && d.message) msg = String(d.message);
      else if ("errors" in d && Array.isArray(d.errors) && d.errors[0]) {
        msg = String(d.errors[0]);
      }
    } else if (typeof err.message === "string") {
      msg = err.message;
    } else if (typeof err.error === "string") {
      msg = err.error;
    }
  } catch {
    msg = await res.text();
  }

  if (res.status === 429) {
    const raw = res.headers.get("Retry-After");
    if (raw && /^\d+$/.test(raw)) retryAfterS = parseInt(raw, 10);
    else {
      const m = /wait about (\d+) seconds/i.exec(msg);
      if (m) retryAfterS = parseInt(m[1], 10);
    }
  }

  throw new ApiError(res.status, String(msg), "", retryAfterS);
}

async function apiFetch<T>(
  url: string,
  init: RequestInit,
  timeoutMs: number,
): Promise<T> {
  const res = await fetchWithTimeout(url, init, timeoutMs);
  return handleResponse<T>(res);
}

export async function checkHealth(): Promise<HealthResponse> {
  // /health is public — no API key to avoid CORS preflight failures
  return apiFetch(`${API_BASE_URL}/health`, { headers: {} }, 5000);
}

export async function ingest(
  repoUrl: string,
  ref?: string,
  forceReindex = false,
): Promise<IngestResponse> {
  const body: Record<string, unknown> = {
    repo_url: repoUrl,
    force_reindex: forceReindex,
  };
  if (ref) body.ref = ref;
  return apiFetch(
    `${API_BASE_URL}/ingest`,
    {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    },
    90_000,
  );
}

export async function getIngestStatus(
  jobId: string,
): Promise<IngestStatusResponse> {
  return apiFetch(
    `${API_BASE_URL}/status/${jobId}`,
    { headers: headers() },
    10_000,
  );
}

export async function chat(body: ChatRequest): Promise<ChatResponse> {
  return apiFetch(
    `${API_BASE_URL}/chat`,
    {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    },
    300_000,
  );
}

export function openChatStream(
  sessionId: string,
  onEvent: (state: string, label: string) => void,
  onError?: (err: Error) => void,
): () => void {
  const url = `${API_BASE_URL}/chat/stream/${sessionId}`;
  const ctrl = new AbortController();
  let reader: ReadableStreamDefaultReader<Uint8Array> | null = null;

  (async () => {
    try {
      const res = await fetch(url, {
        headers: headers(),
        signal: ctrl.signal,
      });
      if (!res.ok || !res.body) {
        onError?.(new Error(`SSE failed: ${res.status}`));
        return;
      }
      reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith("data:")) continue;
          try {
            const data = JSON.parse(line.slice(5).trim()) as {
              state: string;
              label: string;
            };
            onEvent(data.state, data.label);
          } catch {
            /* skip malformed */
          }
        }
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        onError?.(e as Error);
      }
    } finally {
      try {
        await reader?.cancel();
      } catch {
        /* ignore */
      }
    }
  })();

  return () => {
    ctrl.abort();
    void reader?.cancel();
  };
}

export async function getDiagram(
  repoId: string,
  functionName: string,
  depth = 2,
): Promise<DiagramResponse> {
  const fn = encodeURIComponent(functionName);
  return apiFetch(
    `${API_BASE_URL}/diagram/${repoId}/${fn}?depth=${depth}`,
    { headers: headers() },
    30_000,
  );
}

export async function getEvalHealth(
  repoId: string,
  probeAgent = false,
): Promise<EvalHealthResponse> {
  return apiFetch(
    `${API_BASE_URL}/eval/health/${repoId}?probe_agent=${probeAgent}`,
    { headers: headers() },
    120_000,
  );
}

export async function startEval(repoId: string): Promise<{
  job_id: string;
  status: string;
}> {
  return apiFetch(
    `${API_BASE_URL}/eval/run?repo_id=${encodeURIComponent(repoId)}`,
    { method: "POST", headers: headers() },
    10_000,
  );
}

export async function getEvalJobStatus(jobId: string): Promise<EvalJobStatus> {
  return apiFetch(
    `${API_BASE_URL}/eval/status/${jobId}`,
    { headers: headers() },
    15_000,
  );
}

export async function getEvalHistory(): Promise<EvalRun[]> {
  const data = await apiFetch<EvalRun[] | { raw: EvalRun[] }>(
    `${API_BASE_URL}/eval/history`,
    { headers: headers() },
    30_000,
  );
  return Array.isArray(data) ? data : [];
}

export async function compareEvalRuns(
  baselineVersion: string,
  candidateVersion: string,
  tolerance = 0.05,
): Promise<CompareResult> {
  return apiFetch(
    `${API_BASE_URL}/eval/compare`,
    {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({
        baseline_version: baselineVersion,
        candidate_version: candidateVersion,
        tolerance,
      }),
    },
    30_000,
  );
}

export async function getGoldenStatus(): Promise<GoldenStatus> {
  return apiFetch(
    `${API_BASE_URL}/eval/golden-status`,
    { headers: headers() },
    10_000,
  );
}

export async function startGoldenRun(): Promise<{
  job_id: string;
  status: string;
}> {
  return apiFetch(
    `${API_BASE_URL}/eval/golden/run`,
    { method: "POST", headers: headers() },
    15_000,
  );
}

export async function getPlatformUsage(): Promise<UsageSummary> {
  return apiFetch(
    `${API_BASE_URL}/platform/usage`,
    { headers: headers() },
    10_000,
  );
}

export async function getBillingSubscription(): Promise<SubscriptionStatus> {
  return apiFetch(
    `${API_BASE_URL}/billing/subscription`,
    { headers: headers() },
    10_000,
  );
}

export async function getPlatformAudit(
  limit = 50,
): Promise<AuditEvent[]> {
  return apiFetch(
    `${API_BASE_URL}/platform/audit?limit=${limit}`,
    { headers: headers() },
    10_000,
  );
}
