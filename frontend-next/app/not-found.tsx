"use client";

import Link from "next/link";
import { LayoutGrid } from "lucide-react";

export default function NotFound() {
  return (
    <div className="relative min-h-screen flex flex-col items-center justify-center overflow-hidden bg-background">
      {/* Aurora + Grid backgrounds */}
      <div className="pointer-events-none absolute inset-0 aurora-bg animate-aurora" aria-hidden="true" />
      <div className="pointer-events-none absolute inset-0 grid-bg opacity-40" aria-hidden="true" />

      {/* Floating orbs */}
      <div
        className="pointer-events-none absolute -top-32 right-1/4 size-96 rounded-full bg-primary/10 blur-3xl"
        aria-hidden="true"
      />
      <div
        className="pointer-events-none absolute bottom-0 left-1/4 size-72 rounded-full bg-primary/8 blur-3xl"
        aria-hidden="true"
      />

      {/* Content */}
      <div className="relative z-10 flex flex-col items-center text-center px-6">
        {/* Giant gradient 404 */}
        <h1
          className="text-gradient select-none font-display font-bold leading-none"
          style={{ fontSize: "clamp(6rem, 20vw, 14rem)" }}
        >
          404
        </h1>

        <p className="mt-4 text-xl font-display font-semibold text-foreground tracking-tight">
          Page not found
        </p>
        <p className="mt-2 max-w-sm text-sm text-muted-foreground leading-relaxed">
          This route doesn't exist. You may have followed an outdated link, or
          the page was moved.
        </p>

        <Link
          href="/"
          className="mt-8 inline-flex h-11 items-center gap-2 rounded-xl bg-primary px-6 text-sm font-semibold text-primary-foreground glow-primary hover:brightness-110 active:scale-[0.97] transition-all duration-200 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        >
          <LayoutGrid className="h-4 w-4" />
          Return to workspace
        </Link>
      </div>
    </div>
  );
}
