"use client";

import { AppShell } from "@/components/layout/app-shell";
import { OnboardingScreen } from "@/components/workspace/onboarding-screen";
import { useIngestFlow } from "@/lib/hooks/use-ingest-flow";

export default function OnboardingPage() {
  const handleQuickStart = useIngestFlow();

  return (
    <AppShell onQuickStart={(url, ref) => void handleQuickStart(url, ref)}>
      <OnboardingScreen />
    </AppShell>
  );
}
