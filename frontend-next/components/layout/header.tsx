"use client";

import { Menu } from "lucide-react";
import { API_BASE_URL } from "@/lib/constants";
import { useBackendOnline } from "@/lib/hooks/use-backend-health";
import { cn } from "@/lib/utils";
import { BrandLockup } from "@/components/brand/logo-mark";
import { Button } from "@/components/ui/button";

type HeaderProps = {
  onMenuClick?: () => void;
};

export function Header({ onMenuClick }: HeaderProps) {
  const { online, offline } = useBackendOnline();

  return (
    <header className="sticky top-0 z-30 border-b border-border bg-background/80 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-[1400px] items-center justify-between gap-4 px-4 md:px-6">
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="icon-sm"
            className="md:hidden"
            onClick={onMenuClick}
            aria-label="Open navigation menu"
          >
            <Menu className="h-5 w-5" />
          </Button>
          <div className="hidden md:block">
            <BrandLockup showTagline />
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div
            className={cn(
              "flex items-center gap-2 rounded-md border px-2.5 py-1 text-xs font-medium",
              online
                ? "border-success/25 bg-success/10 text-success"
                : offline
                  ? "border-error/25 bg-error/10 text-error"
                  : "border-border bg-surface text-muted-foreground",
            )}
            role="status"
            aria-live="polite"
          >
            <span
              className={cn(
                "h-1.5 w-1.5 rounded-full",
                online ? "bg-success" : offline ? "bg-error" : "bg-tertiary",
              )}
              aria-hidden
            />
            {online ? "API online" : offline ? "API offline" : "Checking…"}
          </div>
          {online && (
            <span className="hidden font-mono text-[11px] text-tertiary sm:inline">
              {API_BASE_URL.replace(/^https?:\/\//, "")}
            </span>
          )}
        </div>
      </div>
    </header>
  );
}
