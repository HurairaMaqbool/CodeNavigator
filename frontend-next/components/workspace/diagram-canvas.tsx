"use client";

import { useEffect, useId, useRef, useState } from "react";
import { AlertTriangle, Download, ZoomIn, ZoomOut, RotateCcw } from "lucide-react";

type DiagramCanvasProps = {
  markdown: string;
  symbolName: string;
  onNodeClick: (nodeLabel: string) => void;
};

export function DiagramCanvas({
  markdown,
  symbolName,
  onNodeClick,
}: DiagramCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const id = useId().replace(/:/g, "");

  // Zoom and Pan states
  const [scale, setScale] = useState(1);
  const [translate, setTranslate] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });

  // Render Mermaid SVG
  useEffect(() => {
    let cancelled = false;
    setError(null);

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

        const { svg } = await mermaid.render(`canvas-mmd-${id}`, markdown);
        if (!cancelled && containerRef.current) {
          containerRef.current.innerHTML = svg;
          // Apply cursor classes to svg nodes
          const nodes = containerRef.current.querySelectorAll(".node");
          nodes.forEach((node) => {
            (node as HTMLElement).style.cursor = "pointer";
          });
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

  // Click handler on diagram nodes
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    function handleSvgClick(event: MouseEvent) {
      const target = event.target as SVGElement;
      const nodeEl = target.closest(".node");
      if (nodeEl) {
        // Retrieve display label text
        const text = nodeEl.querySelector(".label")?.textContent || nodeEl.textContent;
        if (text) {
          onNodeClick(text.trim());
        }
      }
    }

    container.addEventListener("click", handleSvgClick);
    return () => {
      container.removeEventListener("click", handleSvgClick);
    };
  }, [onNodeClick, markdown]);

  // Zoom / Pan events
  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const zoomFactor = 1.1;
    const newScale = e.deltaY < 0 ? scale * zoomFactor : scale / zoomFactor;
    setScale(Math.max(0.2, Math.min(newScale, 5)));
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return; // Left click only
    setIsDragging(true);
    setDragStart({ x: e.clientX - translate.x, y: e.clientY - translate.y });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging) return;
    setTranslate({
      x: e.clientX - dragStart.x,
      y: e.clientY - dragStart.y,
    });
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  const handleZoomIn = () => {
    setScale((prev) => Math.min(prev * 1.2, 5));
  };

  const handleZoomOut = () => {
    setScale((prev) => Math.max(prev / 1.2, 0.2));
  };

  const handleReset = () => {
    setScale(1);
    setTranslate({ x: 0, y: 0 });
  };

  // Export handlers
  const exportSVG = () => {
    const svgEl = containerRef.current?.querySelector("svg");
    if (!svgEl) return;
    const svgString = new XMLSerializer().serializeToString(svgEl);
    const blob = new Blob([svgString], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${symbolName || "diagram"}.svg`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const exportPNG = () => {
    const svgEl = containerRef.current?.querySelector("svg");
    if (!svgEl) return;
    const svgString = new XMLSerializer().serializeToString(svgEl);
    const img = new Image();
    const svgBlob = new Blob([svgString], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(svgBlob);

    img.onload = () => {
      const canvas = document.createElement("canvas");
      const bbox = svgEl.getBoundingClientRect();
      canvas.width = bbox.width * 2 || 1600;
      canvas.height = bbox.height * 2 || 1200;
      const ctx = canvas.getContext("2d");
      if (ctx) {
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.scale(2, 2);
        ctx.drawImage(img, 0, 0);
        const pngUrl = canvas.toDataURL("image/png");
        const a = document.createElement("a");
        a.href = pngUrl;
        a.download = `${symbolName || "diagram"}.png`;
        a.click();
      }
      URL.revokeObjectURL(url);
    };
    img.src = url;
  };

  if (error) {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-warning/40 bg-warning/10 p-4 text-sm">
        <AlertTriangle className="h-4 w-4 shrink-0 text-warning" />
        <div>
          <p className="font-medium text-foreground">Diagram rendering error</p>
          <p className="text-muted-foreground">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="relative w-full h-[580px] rounded-lg border border-border bg-surface-raised overflow-hidden">
      {/* Canvas Viewport */}
      <div
        ref={viewportRef}
        className={`w-full h-full select-none ${
          isDragging ? "cursor-grabbing" : "cursor-grab"
        }`}
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        <div
          ref={containerRef}
          className="w-full h-full flex items-center justify-center transition-transform duration-75 ease-out"
          style={{
            transform: `translate(${translate.x}px, ${translate.y}px) scale(${scale})`,
            transformOrigin: "center center",
          }}
        />
      </div>

      {/* Floating Canvas Controls */}
      <div className="absolute bottom-4 left-4 flex items-center gap-1.5 rounded-lg border border-border bg-surface px-2 py-1.5 shadow-sm">
        <button
          type="button"
          className="p-1 rounded hover:bg-surface-hover text-muted-foreground transition-colors"
          onClick={handleZoomIn}
          title="Zoom In"
        >
          <ZoomIn className="h-4 w-4" />
        </button>
        <button
          type="button"
          className="p-1 rounded hover:bg-surface-hover text-muted-foreground transition-colors"
          onClick={handleZoomOut}
          title="Zoom Out"
        >
          <ZoomOut className="h-4 w-4" />
        </button>
        <button
          type="button"
          className="p-1 rounded hover:bg-surface-hover text-muted-foreground transition-colors"
          onClick={handleReset}
          title="Reset View"
        >
          <RotateCcw className="h-4 w-4" />
        </button>
      </div>

      {/* Export Controls */}
      <div className="absolute top-4 right-4 flex items-center gap-1.5">
        <button
          type="button"
          className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-semibold rounded-lg border border-border bg-surface hover:bg-surface-hover text-foreground transition-colors shadow-sm"
          onClick={exportSVG}
        >
          <Download className="h-3 w-3" />
          SVG
        </button>
        <button
          type="button"
          className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-semibold rounded-lg border border-border bg-surface hover:bg-surface-hover text-foreground transition-colors shadow-sm"
          onClick={exportPNG}
        >
          <Download className="h-3 w-3" />
          PNG
        </button>
      </div>
    </div>
  );
}
