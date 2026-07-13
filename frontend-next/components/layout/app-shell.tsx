"use client";

import { useState, type ReactNode } from "react";
import { Header } from "./header";
import { Sidebar } from "./sidebar";
import { ActiveRepoBar } from "@/components/shared/active-repo-bar";

type AppShellProps = {
  children: ReactNode;
  onQuickStart?: (url: string, ref: string) => void;
};

export function AppShell({ children, onQuickStart }: AppShellProps) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="flex min-h-screen bg-background">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-primary focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-primary-foreground"
      >
        Skip to content
      </a>
      <div className="hidden md:flex md:shrink-0">
        <Sidebar onQuickStart={onQuickStart} className="sticky top-0 h-screen" />
      </div>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            aria-label="Close menu overlay"
            onClick={() => setMobileOpen(false)}
          />
          <Sidebar
            onQuickStart={onQuickStart}
            onClose={() => setMobileOpen(false)}
            className="relative z-50 h-full shadow-elev-3"
          />
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <Header onMenuClick={() => setMobileOpen(true)} />
        <main id="main-content" className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-8 md:px-8">
          <ActiveRepoBar />
          {children}
        </main>
        <footer className="border-t border-border py-5 text-center">
          <p className="text-xs text-tertiary">
            CodeNavigator · Hybrid RAG · Verified citations · Evaluation suite
          </p>
        </footer>
      </div>
    </div>
  );
}
