"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  CircleUser,
  LayoutGrid,
  LineChart,
  MessageSquareCode,
  Network,
  Settings2,
  Terminal,
} from "lucide-react";
import { useApp } from "@/lib/context/app-context";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/onboarding", label: "Workspace",    icon: LayoutGrid },
  { href: "/chat",        label: "Chat",         icon: MessageSquareCode },
  { href: "/architecture",label: "Architecture", icon: Network },
  { href: "/evaluation",  label: "Evaluation",   icon: LineChart },
  { href: "/platform",    label: "Platform",     icon: Settings2 },
] as const;

type SidebarProps = {
  onClose?: () => void;
  className?: string;
};

export function Sidebar({ onClose, className }: SidebarProps) {
  const pathname = usePathname();
  const { repoId } = useApp();

  return (
    <aside
      className={cn(
        "flex h-full w-[68px] flex-col items-center border-r border-border/50 py-4 select-none z-40 relative",
        "bg-sidebar-bg",
        className
      )}
      style={{ background: "var(--sidebar-gradient)" }}
    >
      {/* ── Brand Mark ─────────────────────────────────────── */}
      <Link
        href="/onboarding"
        onClick={onClose}
        aria-label="CodeNavigator home"
        className="group relative flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-primary via-[#a855f7] to-fuchsia-500 text-white shadow-lg shadow-primary/25 hover:brightness-110 hover:scale-105 transition-all duration-200"
      >
        <Terminal className="h-5 w-5 stroke-2" />
        {/* Tooltip */}
        <span className="pointer-events-none absolute left-[calc(100%+14px)] z-50 whitespace-nowrap rounded-lg border border-border bg-surface-raised px-2.5 py-1.5 text-xs font-medium text-foreground opacity-0 shadow-lg transition-opacity duration-150 group-hover:opacity-100">
          CodeNavigator
        </span>
      </Link>

      {/* ── Nav Rail ───────────────────────────────────────── */}
      <nav
        className="flex flex-1 flex-col items-center gap-1.5 mt-8 w-full px-3"
        aria-label="Main navigation"
      >
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(`${href}/`);
          return (
            <Link
              key={href}
              href={href}
              onClick={onClose}
              aria-label={label}
              className={cn(
                "group relative flex h-11 w-11 items-center justify-center rounded-xl transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                active
                  ? "bg-accent text-primary"
                  : "text-muted-foreground hover:bg-surface-hover hover:text-foreground"
              )}
            >
              {/* 2-px active-route accent pill on the left edge */}
              {active && (
                <span
                  className="absolute -left-3 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-r-full bg-primary"
                  style={{ boxShadow: "0 0 8px var(--primary)" }}
                />
              )}

              <Icon className="h-[18px] w-[18px] stroke-[1.75]" />

              {/* Hover tooltip */}
              <span className="pointer-events-none absolute left-[calc(100%+14px)] z-50 whitespace-nowrap rounded-lg border border-border bg-surface-raised px-2.5 py-1.5 text-xs font-medium text-foreground opacity-0 shadow-lg transition-opacity duration-150 group-hover:opacity-100">
                {label}
              </span>
            </Link>
          );
        })}
      </nav>

      {/* ── Bottom Section ─────────────────────────────────── */}
      <div className="flex flex-col items-center gap-4 mt-auto pb-1">
        {/* Live status pulse dot */}
        <div className="group relative flex items-center justify-center cursor-default">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success opacity-60" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-success" />
          </span>
          <span className="pointer-events-none absolute left-[calc(100%+14px)] z-50 whitespace-nowrap rounded-lg border border-border bg-surface-raised px-2.5 py-1.5 text-[10px] font-mono text-success opacity-0 shadow-lg transition-opacity duration-150 group-hover:opacity-100">
            {repoId ? `Active · ${repoId.slice(0, 10)}…` : "System live"}
          </span>
        </div>

        {/* Separator */}
        <div className="h-px w-8 bg-border/60" />

        {/* User avatar */}
        <button
          type="button"
          aria-label="Account settings"
          className="group relative flex h-8 w-8 items-center justify-center rounded-full border border-border/40 bg-surface-raised text-muted-foreground hover:text-foreground hover:border-border transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <CircleUser className="h-[18px] w-[18px] stroke-[1.5]" />
          <span className="pointer-events-none absolute left-[calc(100%+14px)] z-50 whitespace-nowrap rounded-lg border border-border bg-surface-raised px-2.5 py-1.5 text-xs font-medium text-foreground opacity-0 shadow-lg transition-opacity duration-150 group-hover:opacity-100">
            Account
          </span>
        </button>
      </div>
    </aside>
  );
}
