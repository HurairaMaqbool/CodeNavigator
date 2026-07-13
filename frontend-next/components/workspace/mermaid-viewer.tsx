"use client";

import { useEffect, useId, useRef, useState } from "react";
import { AlertTriangle } from "lucide-react";

type MermaidViewerProps = {
  markdown: string;
};

export function MermaidViewer({ markdown }: MermaidViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const id = useId().replace(/:/g, "");

  useEffect(() => {
    let cancelled = false;

    async function render() {
      if (!containerRef.current || !markdown.trim()) return;
      try {
        const mermaid = (await import("mermaid")).default;
        const isDark =
          document.documentElement.classList.contains("dark") ||
          !document.documentElement.classList.contains("light");
        mermaid.initialize({
          startOnLoad: false,
          theme: isDark ? "dark" : "neutral",
          securityLevel: "loose",
        });
        const { svg } = await mermaid.render(`mmd-${id}`, markdown);
        if (!cancelled && containerRef.current) {
          containerRef.current.innerHTML = svg;
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Failed to render diagram");
        }
      }
    }

    void render();
    return () => {
      cancelled = true;
    };
  }, [markdown, id]);

  if (error) {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-warning/40 bg-warning/10 p-4 text-sm">
        <AlertTriangle className="h-4 w-4 shrink-0 text-warning" />
        <div>
          <p className="font-medium text-foreground">Diagram render error</p>
          <p className="text-muted-foreground">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="max-h-[480px] overflow-auto rounded-lg border border-border bg-surface-raised p-4"
      aria-label="Mermaid diagram"
    />
  );
}
