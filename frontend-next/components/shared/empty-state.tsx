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
  return (
    <div className="empty-state-panel">
      {icon && (
        <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-lg border border-border bg-surface-raised text-muted-foreground">
          {icon}
        </div>
      )}
      <h3 className="text-base font-semibold tracking-tight text-foreground">
        {title}
      </h3>
      <p className="mt-2 max-w-sm text-sm leading-relaxed text-muted-foreground">
        {description}
      </p>
      {action && <div className="mt-6">{action}</div>}
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
