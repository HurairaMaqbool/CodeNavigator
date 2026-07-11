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
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border bg-surface/50 px-6 py-12 text-center">
      {icon && <div className="mb-4 text-muted-foreground">{icon}</div>}
      <h3 className="text-lg font-medium text-foreground">{title}</h3>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">
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
      className="flex items-start gap-3 rounded-lg border border-error/30 bg-error/10 p-4 text-sm text-error"
      role="alert"
    >
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div className="flex-1">
        <p className="font-medium">Couldn&apos;t reach the server</p>
        <p className="mt-1 text-error/90">{message}</p>
        {onRetry && (
          <Button
            variant="outline"
            size="sm"
            className="mt-3 border-error/40"
            onClick={onRetry}
          >
            <RefreshCw className="h-3 w-3" />
            Retry
          </Button>
        )}
      </div>
    </div>
  );
}
