import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function truncateId(id: string, max = 22): string {
  if (!id) return "";
  return id.length <= max ? id : `${id.slice(0, max)}…`;
}

/** Stable React key / select value for an eval history row. */
export function getEvalRunKey(run: { run_id?: string; version?: string; timestamp?: string }): string {
  if (run.run_id) return run.run_id;
  const ver = run.version ?? "unknown";
  const ts = run.timestamp ?? "";
  return ts ? `${ver}::${ts}` : ver;
}

/** Human-readable dropdown label — truncation is display-only, never used as a key. */
export function formatEvalRunLabel(run: {
  version?: string;
  timestamp?: string;
  git_sha?: string;
}): string {
  const ver = run.version ?? "unknown";
  const shortSha = run.git_sha ? truncateId(run.git_sha, 7) : "";
  const when = run.timestamp
    ? new Date(run.timestamp).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "";
  const parts = [ver];
  if (shortSha && shortSha !== ver) parts.push(shortSha);
  if (when) parts.push(when);
  return parts.join(" · ");
}
