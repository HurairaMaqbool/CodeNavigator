"use client";

import { useState, type ReactNode } from "react";
import { Header } from "./header";
import { Sidebar } from "./sidebar";

type AppShellProps = {
  children: ReactNode;
  onQuickStart?: (url: string, ref: string) => void;
};

export function AppShell({ children, onQuickStart }: AppShellProps) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="flex min-h-screen bg-background">
      <div className="hidden md:flex md:shrink-0">
        <Sidebar onQuickStart={onQuickStart} className="sticky top-0 h-screen" />
      </div>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-black/50"
            aria-label="Close menu overlay"
            onClick={() => setMobileOpen(false)}
          />
          <Sidebar
            onQuickStart={onQuickStart}
            onClose={() => setMobileOpen(false)}
            className="relative z-50 h-full shadow-xl"
          />
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <Header onMenuClick={() => setMobileOpen(true)} />
        <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 md:px-6">
          {children}
        </main>
        <footer className="border-t border-border py-4 text-center text-xs text-muted-foreground">
          CodeNavigator v1.0.0 · Hybrid RAG · Citations · Eval
        </footer>
      </div>
    </div>
  );
}
