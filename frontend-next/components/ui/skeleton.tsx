import { cn } from "@/lib/utils";

export function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "animate-pulse rounded-lg bg-muted",
        className,
      )}
      {...props}
    />
  );
}

export function ScreenSkeleton({ cards = 3 }: { cards?: number }) {
  return (
    <div className="space-y-4" aria-hidden="true">
      <Skeleton className="h-8 w-48" />
      <div className="grid gap-4 sm:grid-cols-3">
        {Array.from({ length: cards }).map((_, i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
      <Skeleton className="h-40" />
    </div>
  );
}
