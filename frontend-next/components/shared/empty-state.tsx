"use client";

import { AlertCircle, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  // Determine if we should render a signature custom illustration based on title
  const isNoRepo = title.toLowerCase().includes("repository") || title.toLowerCase().includes("connect");
  const isNoSymbol = title.toLowerCase().includes("symbol") || title.toLowerCase().includes("select");
  const isNoResults = title.toLowerCase().includes("result") || title.toLowerCase().includes("no search");

  return (
    <div className="empty-state-panel relative overflow-hidden group">
      {/* Signature mesh background visual motif */}
      <div className="absolute -right-16 -top-16 w-48 h-48 rounded-full bg-primary/5 blur-3xl group-hover:bg-primary/10 transition-all duration-700 pointer-events-none" />
      <div className="absolute -left-16 -bottom-16 w-48 h-48 rounded-full bg-success/5 blur-3xl group-hover:bg-success/10 transition-all duration-700 pointer-events-none" />

      {/* Modern Line-Art Illustrations (Phase 2, Moment 4) */}
      {isNoRepo ? (
        <div className="mb-6 flex h-20 w-20 items-center justify-center rounded-2xl border border-border bg-surface-raised shadow-elev-1 relative z-10">
          <svg className="h-10 w-10 text-primary" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect x="6" y="8" width="10" height="10" rx="3" stroke="currentColor" strokeWidth="1.5" strokeDasharray="2 2" />
            <rect x="24" y="8" width="10" height="10" rx="3" stroke="currentColor" strokeWidth="1.5" />
            <rect x="15" y="24" width="10" height="10" rx="3" stroke="currentColor" strokeWidth="1.5" />
            <path d="M11 18V21C11 22 12 23 13 23H15" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            <path d="M29 18V21C29 22 28 23 27 23H25" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            <circle cx="11" cy="18" r="1.5" fill="currentColor" />
            <circle cx="29" cy="18" r="1.5" fill="currentColor" />
            <circle cx="20" cy="24" r="1.5" fill="currentColor" />
          </svg>
        </div>
      ) : isNoSymbol ? (
        <div className="mb-6 flex h-20 w-20 items-center justify-center rounded-2xl border border-border bg-surface-raised shadow-elev-1 relative z-10">
          <svg className="h-10 w-10 text-primary" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="20" cy="20" r="12" stroke="currentColor" strokeWidth="1.5" strokeDasharray="3 3" />
            <circle cx="20" cy="20" r="6" stroke="currentColor" strokeWidth="1.5" />
            <line x1="20" y1="2" x2="20" y2="8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            <line x1="20" y1="32" x2="20" y2="38" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            <line x1="2" y1="20" x2="8" y2="20" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            <line x1="32" y1="20" x2="38" y2="20" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </div>
      ) : isNoResults ? (
        <div className="mb-6 flex h-20 w-20 items-center justify-center rounded-2xl border border-border bg-surface-raised shadow-elev-1 relative z-10">
          <svg className="h-10 w-10 text-primary" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="18" cy="18" r="8" stroke="currentColor" strokeWidth="1.5" />
            <line x1="24" y1="24" x2="34" y2="34" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            <path d="M12 18H24" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeDasharray="2 2" />
          </svg>
        </div>
      ) : icon ? (
        <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-lg border border-border bg-surface-raised text-muted-foreground relative z-10">
          {icon}
        </div>
      ) : null}

      <h3 className="text-base font-display text-foreground relative z-10">
        {title}
      </h3>
      <p className="mt-2 max-w-sm text-sm leading-relaxed text-muted-foreground relative z-10">
        {description}
      </p>
      {action && <div className="mt-6 relative z-10">{action}</div>}
    </div>
  );
}

export function QueryError({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div
      className="flex items-start gap-3 rounded-lg border border-error/30 bg-error/10 p-4 text-sm"
      role="alert"
    >
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-error" aria-hidden />
      <div className="flex-1">
        <p className="font-medium text-error">Couldn&apos;t reach the server</p>
        <p className="mt-1 text-error/90">{message}</p>
        {onRetry && (
          <Button variant="outline" size="sm" className="mt-3" onClick={onRetry}>
            <RefreshCw className="h-3.5 w-3.5" />
            Try again
          </Button>
        )}
      </div>
    </div>
  );
}
