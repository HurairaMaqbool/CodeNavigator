import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function SectionHeader({
  title,
  caption,
  className,
  dense,
}: {
  title: string;
  caption?: string;
  className?: string;
  dense?: boolean;
}) {
  return (
    <header className={cn(dense ? "mb-4" : "mb-6", className)}>
      <h2 className="text-title">
        {title}
      </h2>
      {caption && (
        <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-muted-foreground">
          {caption}
        </p>
      )}
    </header>
  );
}

type StatCardProps = {
  label: string;
  value: ReactNode;
  className?: string;
  status?: "ok" | "warn" | "error" | "neutral";
};

const statusDot: Record<NonNullable<StatCardProps["status"]>, string> = {
  ok: "bg-success",
  warn: "bg-warning",
  error: "bg-error",
  neutral: "bg-tertiary",
};

export function StatCard({
  label,
  value,
  className,
  status = "neutral",
}: StatCardProps) {
  return (
    <div
      className={cn(
        "card-surface group flex flex-col gap-3 p-6 transition-all duration-200 hover:border-border-strong hover:-translate-y-[1px]",
        className,
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <p className="micro-label">{label}</p>
        <span
          className={cn(
            "h-2 w-2 shrink-0 rounded-full transition-transform duration-300 group-hover:scale-125",
            statusDot[status],
          )}
          aria-hidden
        />
      </div>
      <p
        className={cn(
          "text-display truncate max-w-full",
          typeof value === "string" && value.length > 12 && "text-base sm:text-lg font-mono"
        )}
        title={typeof value === "string" ? value : undefined}
      >
        {value}
      </p>
    </div>
  );
}
