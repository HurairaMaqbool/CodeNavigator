"use client";

import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { ingest } from "@/lib/api";
import { ApiError } from "@/lib/types";
import { useApp } from "@/lib/context/app-context";
import { useBackendOnline } from "@/lib/hooks/use-backend-health";

export function useIngestFlow() {
  const router = useRouter();
  const { setRepoId } = useApp();
  const { online: backendOnline } = useBackendOnline();

  return async (repoUrl: string, ref: string) => {
    if (!backendOnline) {
      toast.error("Backend offline — start uvicorn on port 8000");
      return;
    }
    try {
      const res = await ingest(repoUrl, ref);
      setRepoId(res.job_id);
      toast.success("Indexing started");
      router.push("/onboarding");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Ingest failed");
    }
  };
}
