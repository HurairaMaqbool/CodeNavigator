import type { EvalHealthResponse, IngestStatusResponse } from "@/lib/types";
import { repoIsReady } from "@/lib/constants";

/** Unified chunk summary for Connect, Eval, and Platform bars. */
export function formatChunkSummary(
  status?: IngestStatusResponse | null,
  evalHealth?: EvalHealthResponse | null,
): string {
  const details = evalHealth?.details ?? {};
  const chroma =
    typeof details.chroma_chunks === "number"
      ? details.chroma_chunks
      : typeof details.chroma_chunk_count === "number"
        ? details.chroma_chunk_count
        : null;
  const indexed =
    typeof details.chunks_created === "number"
      ? details.chunks_created
      : status?.chunks_created ?? null;

  if (indexed != null && chroma != null) {
    if (indexed === chroma) return String(indexed);
    return `${indexed} meta / ${chroma} vectors`;
  }
  if (chroma != null) return String(chroma);
  if (indexed != null) return String(indexed);
  if (status?.chunks_created != null) return String(status.chunks_created);
  return "—";
}

export function formatIndexState(
  status?: IngestStatusResponse | null,
  evalHealth?: EvalHealthResponse | null,
): { label: string; ready: boolean; syncing: boolean } {
  const readyFromStatus = status ? repoIsReady(status) : false;
  const readyFromEval = evalHealth?.ok === true;
  const ready = readyFromStatus && (evalHealth ? readyFromEval : true);
  const syncing = Boolean(status && !readyFromStatus && status.status !== "failed");
  const failed = status?.status === "failed";

  let label = "No repo";
  if (status) {
    if (ready) label = "Ready";
    else if (failed) label = "Failed";
    else if (syncing) label = "Indexing…";
    else label = status.sync_status ?? "Unknown";
  }

  return { label, ready, syncing };
}
