"use client";

import { usePathname, useRouter } from "next/navigation";
import { Bell, Menu, Search } from "lucide-react";
import { useBackendOnline } from "@/lib/hooks/use-backend-health";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

type HeaderProps = {
  onMenuClick?: () => void;
};

export function Header({ onMenuClick }: HeaderProps) {
  const { online } = useBackendOnline();
  const pathname = usePathname();
  const router = useRouter();

  // Resolve breadcrumbs dynamically based on path
  const getBreadcrumb = () => {
    if (pathname === "/onboarding") return { subtitle: "OVERVIEW", title: "Workspace" };
    if (pathname === "/chat") return { subtitle: "WORKSPACE", title: "Chat" };
    if (pathname === "/architecture") return { subtitle: "EXPLORE", title: "Architecture" };
    if (pathname === "/evaluation") return { subtitle: "QUALITY", title: "Evaluation" };
    if (pathname === "/platform") return { subtitle: "SYSTEM", title: "Platform" };
    return { subtitle: "CODENAVIGATOR", title: "Console" };
  };

  const breadcrumb = getBreadcrumb();

  return (
    <header className="sticky top-0 z-30 flex h-14 w-full items-center border-b border-border/40 bg-background/80 backdrop-blur-md px-4 md:px-6 select-none">
      <div className="mx-auto flex w-full max-w-[1400px] items-center justify-between gap-4">
        {/* Left Side: Mobile Menu Trigger + Breadcrumb */}
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="icon-sm"
            className="md:hidden text-muted-foreground hover:text-foreground"
            onClick={onMenuClick}
            aria-label="Open navigation menu"
          >
            <Menu className="h-5 w-5" />
          </Button>

          <div className="flex flex-col text-left">
            <span className="text-[10px] font-semibold tracking-wider text-muted-foreground font-sans">
              {breadcrumb.subtitle}
            </span>
            <span className="text-sm font-semibold tracking-tight text-foreground -mt-0.5">
              {breadcrumb.title}
            </span>
          </div>
        </div>

        {/* Right Side: Command-Palette Search, Notifications, Avatar */}
        <div className="flex items-center gap-4">
          {/* Command Palette Search Box */}
          <button
            type="button"
            className="hidden sm:flex w-64 items-center justify-between rounded-lg border border-border/40 bg-surface px-3 py-1.5 text-xs text-muted-foreground hover:bg-surface-hover hover:border-border transition-all duration-200 cursor-pointer"
            onClick={() => router.push("/onboarding")}
          >
            <div className="flex items-center gap-2">
              <Search className="h-3.5 w-3.5" />
              <span>Search symbols, files...</span>
            </div>
            <kbd className="flex h-5 items-center gap-0.5 rounded border border-border bg-surface-elevated px-1.5 font-mono text-[9px] font-medium text-tertiary select-none">
              <span>⌘</span>K
            </kbd>
          </button>

          {/* Notifications Bell */}
          <button
            type="button"
            className="relative flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground hover:bg-surface transition-all duration-200 cursor-pointer"
            aria-label="View notifications"
          >
            <Bell className="h-4 w-4" />
            <span className="absolute right-2.5 top-2.5 flex h-1.5 w-1.5 rounded-full bg-primary" />
          </button>

          {/* User Profile Avatar */}
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-tr from-primary to-accent border border-border/30 text-white font-sans text-xs font-semibold cursor-pointer hover:scale-105 transition-all duration-200 select-none shadow-md shadow-primary/10">
            HM
          </div>

          {/* Live pipeline API indicator */}
          <div className="flex items-center gap-1.5">
            <span className={cn(
              "relative flex h-1.5 w-1.5 rounded-full",
              online ? "bg-success shadow-[0_0_8px_var(--success)]" : "bg-warning animate-pulse"
            )} />
          </div>
        </div>
      </div>
    </header>
  );
}
