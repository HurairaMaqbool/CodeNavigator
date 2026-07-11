"use client";

import { Menu } from "lucide-react";
import { API_BASE_URL, BRAND } from "@/lib/constants";
import { useBackendOnline } from "@/lib/hooks/use-backend-health";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

type HeaderProps = {
  onMenuClick?: () => void;
};

export function Header({ onMenuClick }: HeaderProps) {
  const { online, offline } = useBackendOnline();

  return (
    <header className="sticky top-0 z-30 border-b border-border bg-surface/95 backdrop-blur supports-[backdrop-filter]:bg-surface/80">
      <div className="mx-auto flex h-14 max-w-[1400px] items-center justify-between gap-4 px-4 md:px-6">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden"
            onClick={onMenuClick}
            aria-label="Open navigation menu"
          >
            <Menu className="h-5 w-5" />
          </Button>
          <div className="hidden items-center gap-2 md:flex">
            <span className="text-xl" aria-hidden>
              {BRAND.logo}
            </span>
            <div>
              <p className="text-sm font-semibold text-foreground">
                {BRAND.name}
              </p>
              <p className="text-xs text-muted-foreground">{BRAND.tagline}</p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div
            className={cn(
              "flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium",
              online
                ? "bg-success/10 text-success"
                : offline
                  ? "bg-error/10 text-error"
                  : "bg-muted text-muted-foreground",
            )}
            role="status"
            aria-live="polite"
          >
            <span
              className={cn(
                "h-2 w-2 rounded-full",
                online ? "animate-pulse bg-success" : "bg-muted-foreground",
              )}
              aria-hidden
            />
            {online ? "API online" : offline ? "API offline" : "Checking…"}
          </div>
          {online && (
            <span className="hidden font-mono text-xs text-muted-foreground sm:inline">
              {API_BASE_URL}
            </span>
          )}
        </div>
      </div>
    </header>
  );
}
