import { toast } from "sonner";
import { getEvalJobStatus } from "@/lib/api";
import { ApiError, type EvalJobStatus } from "@/lib/types";

export type PollEvalJobOptions = {
  pollIntervalMs?: number;
  /** Hard stop — show error and clear loading (default 10 min). */
  maxMs?: number;
  /** Soft hint while still running (default 90s). */
  slowAfterMs?: number;
  onStatus?: (status: string, elapsedMs: number) => void;
  /** Suppress slow-progress toast (automation paths). */
  silent?: boolean;
};

const DEFAULT_POLL_MS = 3000;
const DEFAULT_MAX_MS = 600_000;
const DEFAULT_SLOW_MS = 90_000;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Poll GET /eval/status/{jobId} until done, error, or timeout.
 * Surfaces a slow-progress toast and always terminates (never infinite).
 */
export async function pollEvalJob(
  jobId: string,
  options: PollEvalJobOptions = {},
): Promise<EvalJobStatus> {
  const pollIntervalMs = options.pollIntervalMs ?? DEFAULT_POLL_MS;
  const maxMs = options.maxMs ?? DEFAULT_MAX_MS;
  const slowAfterMs = options.slowAfterMs ?? DEFAULT_SLOW_MS;
  const toastId = `eval-job-${jobId}`;
  const t0 = Date.now();
  let slowNotified = false;

  while (Date.now() - t0 < maxMs) {
    const elapsed = Date.now() - t0;
    let status: EvalJobStatus;
    try {
      status = await getEvalJobStatus(jobId);
    } catch (err) {
      if (err instanceof ApiError && err.statusCode === 404) {
        throw new ApiError(
          404,
          "Eval job not found — the API may have restarted. Try running again.",
        );
      }
      throw err;
    }

    options.onStatus?.(status.status, elapsed);

    if (
      !options.silent &&
      !slowNotified &&
      elapsed >= slowAfterMs &&
      status.status === "running"
    ) {
      slowNotified = true;
      toast.info(
        "This is taking longer than expected — large evals can run several minutes.",
        { id: toastId, duration: 8000 },
      );
    }

    if (status.status === "done" || status.status === "error") {
      return status;
    }

    await sleep(pollIntervalMs);
  }

  throw new Error(
    `Eval job timed out after ${Math.round(maxMs / 1000)}s with no final status.`,
  );
}

export function formatEvalJobError(status: EvalJobStatus): string {
  if (status.error) return status.error;
  if (status.status === "error") return "Eval failed";
  return "Eval finished without a result";
}
