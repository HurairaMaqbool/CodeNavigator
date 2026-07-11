import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function SectionHeader({
  title,
  caption,
  className,
}: {
  title: string;
  caption?: string;
  className?: string;
}) {
  return (
    <div className={cn("mb-4", className)}>
      <h2 className="text-xl font-semibold text-foreground">{title}</h2>
      {caption && (
        <p className="mt-1 text-sm text-muted-foreground">{caption}</p>
      )}
      <div className="mt-2 h-0.5 w-12 rounded-full bg-primary" />
    </div>
  );
}

export function StatCard({
  label,
  value,
  className,
}: {
  label: string;
  value: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-xl border border-border bg-surface p-4 shadow-sm",
        className,
      )}
    >
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className="mt-1 text-2xl font-semibold text-foreground">{value}</p>
    </div>
  );
}
