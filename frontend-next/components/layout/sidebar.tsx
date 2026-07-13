"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  BarChart3,
  Link2,
  MessageSquare,
  Network,
  Settings,
  X,
} from "lucide-react";
import { QUICK_START_REPOS } from "@/lib/constants";
import { useApp } from "@/lib/context/app-context";
import { truncateId } from "@/lib/utils";
import { cn } from "@/lib/utils";
import { BrandLockup } from "@/components/brand/logo-mark";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "./theme-toggle";

const NAV = [
  { href: "/onboarding", label: "Connect", icon: Link2 },
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/evaluation", label: "Evaluation", icon: BarChart3 },
  { href: "/architecture", label: "Architecture", icon: Network },
  { href: "/platform", label: "Platform", icon: Settings },
] as const;

type SidebarProps = {
  onQuickStart?: (url: string, ref: string) => void;
  onClose?: () => void;
  className?: string;
};

export function Sidebar({ onQuickStart, onClose, className }: SidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { repoId, clearSession } = useApp();

  return (
    <aside
      className={cn(
        "flex h-full w-[260px] flex-col border-r border-border bg-surface",
        className,
      )}
    >
      <div className="flex items-center justify-between border-b border-border px-4 py-4">
        <BrandLockup />
        {onClose && (
          <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close menu">
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>

      <nav className="flex-1 px-3 py-4 space-y-6" aria-label="Main navigation">
        <div>
          <p className="micro-label mb-2 px-3">Workspace</p>
          <ul className="space-y-0.5">
            {NAV.map(({ href, label, icon: Icon }) => {
              const active =
                pathname === href || pathname.startsWith(`${href}/`);
              return (
                <li key={href}>
                  <Link
                    href={href}
                    onClick={onClose}
                    className={cn(
                      "relative flex min-h-[38px] items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors duration-150",
                      active
                        ? "bg-primary/8 text-primary before:absolute before:left-0 before:top-2 before:bottom-2 before:w-[2px] before:rounded-r before:bg-primary"
                        : "text-muted-foreground hover:bg-surface-hover hover:text-foreground",
                    )}
                  >
                    <Icon
                      className={cn(
                        "h-[18px] w-[18px] shrink-0 stroke-[1.75]",
                        active ? "text-primary" : "",
                      )}
                      aria-hidden
                    />
                    {label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>

        <div>
          <p className="micro-label mb-2 px-3">Quick start</p>
          <div className="space-y-0.5 px-1">
            {QUICK_START_REPOS.map((r) => (
              <button
                key={r.url}
                type="button"
                className="flex w-full min-h-[32px] items-center rounded-md px-2.5 py-1 text-left text-xs font-medium text-muted-foreground hover:bg-surface-hover hover:text-foreground transition-colors duration-150 cursor-pointer"
                onClick={() => onQuickStart?.(r.url, r.ref)}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>
      </nav>

      <div className="space-y-4 border-t border-border p-4">
        <div className="flex items-center justify-between">
          <span className="micro-label">Appearance</span>
          <ThemeToggle compact />
        </div>

        {repoId && (
          <div className="rounded-lg border border-border bg-surface-raised p-3">
            <p className="micro-label mb-1.5">Active repository</p>
            <p className="truncate font-mono text-xs text-foreground">
              {truncateId(repoId)}
            </p>
          </div>
        )}

        <Button
          variant="secondary"
          size="sm"
          className="w-full text-muted-foreground hover:text-error hover:border-error/25 hover:bg-error/10 transition-all duration-150"
          onClick={() => {
            clearSession();
            onClose?.();
            router.push("/onboarding");
          }}
        >
          Clear session
        </Button>
      </div>
    </aside>
  );
}
