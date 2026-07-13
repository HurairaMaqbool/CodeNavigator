"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { useState, type ReactNode } from "react";
import { Toaster } from "sonner";
import { AppProvider } from "@/lib/context/app-context";
import { RepoSyncBridge } from "@/components/shared/repo-sync-bridge";
import { EvalAutomationBridge } from "@/components/evaluation/eval-automation-bridge";

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            refetchOnWindowFocus: true,
            retry: 1,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false}>
        <AppProvider>
          <RepoSyncBridge />
          <EvalAutomationBridge />
          {children}
          <Toaster
            position="top-right"
            closeButton
            toastOptions={{
              classNames: {
                toast:
                  "rounded-lg border border-border bg-surface-raised text-foreground shadow-elev-2",
              },
            }}
          />
        </AppProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
