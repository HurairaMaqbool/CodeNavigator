import { CHAT_QUERY_SUCCESS_EVENT } from "@/lib/eval-automation-state";

export type ChatQuerySuccessDetail = {
  repoId: string;
};

/** Fire-and-forget signal after a successful chat answer (non-blocking). */
export function notifyChatQuerySuccess(repoId: string): void {
  if (typeof window === "undefined") return;
  try {
    window.dispatchEvent(
      new CustomEvent<ChatQuerySuccessDetail>(CHAT_QUERY_SUCCESS_EVENT, {
        detail: { repoId },
      }),
    );
  } catch {
    /* ignore */
  }
}
