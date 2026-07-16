import { cn } from "@/lib/utils";

type LogoMarkProps = {
  className?: string;
  size?: "sm" | "md" | "lg";
  animated?: boolean;
};

const sizes = {
  sm: "h-6 w-6",
  md: "h-8 w-8",
  lg: "h-10 w-10",
};

/** Minimal geometric mark — no emoji, no generic AI sparkle. */
export function LogoMark({ className, size = "md", animated = false }: LogoMarkProps) {
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
      {/* Outer bracket paths: slide in/out slightly if animated */}
      <path
        d="M10 16L7 13M10 16L7 19"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
        className={cn(animated && "animate-pulse origin-center")}
      />
      <path
        d="M22 16L25 13M22 16L25 19"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
        className={cn(animated && "animate-pulse origin-center")}
      />
      {/* Central node pulse / spin motif */}
      <circle 
        cx="16" 
        cy="16" 
        r="2.25" 
        fill="currentColor" 
        className={cn(animated && "animate-ping origin-center scale-110")}
      />
      <circle 
        cx="16" 
        cy="16" 
        r="2.25" 
        fill="currentColor" 
      />
      <path
        d="M13.5 16H18.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        opacity="0.6"
        className={cn(animated && "animate-pulse")}
      />
    </svg>
  );
}

export function BrandLockup({
  className,
  showTagline = false,
  animated = false,
}: {
  className?: string;
  showTagline?: boolean;
  animated?: boolean;
}) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <LogoMark size="md" animated={animated} />
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
