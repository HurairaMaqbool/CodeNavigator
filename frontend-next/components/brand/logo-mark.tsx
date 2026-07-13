import { cn } from "@/lib/utils";

type LogoMarkProps = {
  className?: string;
  size?: "sm" | "md" | "lg";
};

const sizes = {
  sm: "h-6 w-6",
  md: "h-8 w-8",
  lg: "h-10 w-10",
};

/** Minimal geometric mark — no emoji, no generic AI sparkle. */
export function LogoMark({ className, size = "md" }: LogoMarkProps) {
  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn(sizes[size], "shrink-0 text-primary", className)}
      aria-hidden
    >
      <rect
        x="2"
        y="4"
        width="28"
        height="24"
        rx="7"
        fill="currentColor"
        opacity="0.12"
      />
      <path
        d="M10 16L7 13M10 16L7 19"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M22 16L25 13M22 16L25 19"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="16" cy="16" r="2.25" fill="currentColor" />
      <path
        d="M13.5 16H18.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        opacity="0.6"
      />
    </svg>
  );
}

export function BrandLockup({
  className,
  showTagline = false,
}: {
  className?: string;
  showTagline?: boolean;
}) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <LogoMark size="md" />
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold leading-tight tracking-tight text-foreground">
          CodeNavigator
        </p>
        {showTagline && (
          <p className="truncate text-xs text-muted-foreground">
            Understand any codebase in minutes
          </p>
        )}
      </div>
    </div>
  );
}
