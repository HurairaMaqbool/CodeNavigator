"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  LayoutDashboard,
  Settings,
  X,
} from "lucide-react";
import { BRAND, QUICK_START_REPOS } from "@/lib/constants";
import { useApp } from "@/lib/context/app-context";
import { truncateId } from "@/lib/utils";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "./theme-toggle";

const NAV = [
  { href: "/workspace", label: "Workspace", icon: LayoutDashboard },
  { href: "/evaluation", label: "Evaluation", icon: BarChart3 },
  { href: "/platform", label: "Platform", icon: Settings },
] as const;

type SidebarProps = {
  onQuickStart?: (url: string, ref: string) => void;
  onClose?: () => void;
  className?: string;
};

export function Sidebar({ onQuickStart, onClose, className }: SidebarProps) {
  const pathname = usePathname();
  const { repoId, clearSession } = useApp();

  return (
    <aside
      className={cn(
        "flex h-full w-64 flex-col border-r border-border bg-surface-elevated",
        className,
      )}
    >
      <div className="flex items-center justify-between border-b border-border p-4">
        <div className="flex items-center gap-2">
          <span className="text-xl" aria-hidden>
            {BRAND.logo}
          </span>
          <span className="font-semibold text-foreground">{BRAND.name}</span>
        </div>
        {onClose && (
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close menu">
            <X className="h-5 w-5" />
          </Button>
        )}
      </div>

      <nav className="flex-1 space-y-1 p-3" aria-label="Main navigation">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(`${href}/`);
          return (
            <Link
              key={href}
              href={href}
              onClick={onClose}
              className={cn(
                "flex min-h-[44px] items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-primary/15 text-primary"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              <Icon className="h-4 w-4 shrink-0" aria-hidden />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="space-y-3 border-t border-border p-4">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Appearance
          </span>
          <ThemeToggle />
        </div>

        {repoId && (
          <div className="rounded-lg bg-muted/50 p-3 text-xs">
            <p className="mb-1 font-medium text-muted-foreground">Active repo</p>
            <p className="font-mono text-foreground">{truncateId(repoId)}</p>
          </div>
        )}

        <Button
          variant="secondary"
          className="w-full"
          onClick={() => {
            clearSession();
            onClose?.();
          }}
        >
          Clear session
        </Button>

        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Quick start
          </p>
          <div className="flex flex-col gap-2">
            {QUICK_START_REPOS.map((r) => (
              <Button
                key={r.url}
                variant="outline"
                size="sm"
                className="w-full justify-start"
                onClick={() => onQuickStart?.(r.url, r.ref)}
              >
                {r.label}
              </Button>
            ))}
          </div>
        </div>
      </div>
    </aside>
  );
}
