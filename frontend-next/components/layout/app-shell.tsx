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
    <div className="flex h-screen bg-[#0f1012] font-sans antialiased text-foreground overflow-hidden">
      {/* Skip Navigation Link */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-primary focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-primary-foreground"
      >
        Skip to content
      </a>

      {/* ── Ambient Background: Faint 48px Grid + Drifting Aurora ── */}
      <div className="fixed inset-0 z-0 pointer-events-none overflow-hidden" aria-hidden="true">
        {/* Drifting Aurora */}
        <div className="absolute inset-0 aurora-bg animate-aurora" />
        
        {/* 48px Grid */}
        <div className="absolute inset-0 grid-bg opacity-40" />
      </div>

      {/* ── Sidebar — Fixed to viewport, NEVER scrolls ── */}
      <aside
        className="hidden md:flex fixed inset-y-0 left-0 z-40 w-[68px] flex-col"
        aria-label="Navigation sidebar"
      >
        <Sidebar />
      </aside>

      {/* Mobile Sidebar Overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden flex">
          <button
            type="button"
            className="absolute inset-0 bg-black/60 backdrop-blur-sm transition-opacity"
            aria-label="Close menu overlay"
            onClick={() => setMobileOpen(false)}
          />
          <Sidebar
            onClose={() => setMobileOpen(false)}
            className="relative z-50 h-full shadow-elev-3 animate-fade-in"
          />
        </div>
      )}

      {/* ── Content Column — offset from fixed sidebar, scrolls independently ── */}
      <div className="flex flex-col flex-1 md:ml-[68px] min-w-0 relative z-10 h-screen overflow-hidden">
        {/* Sticky topbar within this column */}
        <Header onMenuClick={() => setMobileOpen(true)} />

        {/* Scrollable main content area — sidebar is unaffected */}
        <main
          id="main-content"
          className="flex-1 overflow-y-auto"
        >
          <div className="mx-auto w-full max-w-[1400px] px-4 py-8 md:px-8">
            <ActiveRepoBar />
            {children}
          </div>
          <footer className="border-t border-border/40 py-5 text-center">
            <p className="text-xs text-tertiary font-mono">
              CodeNavigator · Hybrid RAG · Grounded Citations · Evaluation Suite
            </p>
          </footer>
        </main>
      </div>
    </div>
  );
}
