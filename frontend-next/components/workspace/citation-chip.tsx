import type { ChatSource } from "@/lib/types";
import { cn } from "@/lib/utils";
import { FileCode, Layers } from "lucide-react";

export function CitationChip({ source }: { source: ChatSource }) {
  const linesLabel = source.lines 
    ? `:${source.lines}` 
    : source.start_line != null 
      ? `:${source.start_line}-${source.end_line}` 
      : "";
  const label = `${source.file_path}${linesLabel}`;

  // Extract filename for clear visual display
  const fileName = source.file_path.split("/").pop() || source.file_path;
  const pathPrefix = source.file_path.includes("/") 
    ? source.file_path.split("/").slice(0, -1).join("/") + "/" 
    : "";

  return (
    <div className="relative group/citation inline-block shrink-0">
      {/* Premium Interactive Chip */}
      <span
        className={cn(
          "inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface-raised px-2.5 py-1",
          "font-mono text-xs text-muted-foreground select-all transition-all duration-200 cursor-pointer",
          "hover:border-primary/45 hover:bg-primary-tint hover:text-primary hover:shadow-elev-1 active:scale-95"
        )}
      >
        <FileCode className="h-3.5 w-3.5 text-tertiary group-hover/citation:text-primary transition-colors" />
        <span className="truncate max-w-[160px]">
          <span className="opacity-40 text-[10px]">{pathPrefix}</span>
          <span className="font-semibold text-foreground group-hover/citation:text-primary transition-colors">{fileName}</span>
          <span className="text-primary/70">{linesLabel}</span>
        </span>
      </span>

      {/* Mini-Code-Snippet Tooltip Hover Preview (Phase 4, Moment 1) */}
      <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 p-3 rounded-xl border border-border bg-surface shadow-elev-3 opacity-0 scale-95 pointer-events-none group-hover/citation:opacity-100 group-hover/citation:scale-100 transition-all duration-200 origin-bottom z-50">
        <div className="flex items-center gap-1.5 border-b border-border/60 pb-1.5 mb-2">
          <Layers className="h-3.5 w-3.5 text-primary" />
          <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Source Context</span>
        </div>
        <div className="space-y-1">
          <div className="flex items-center justify-between text-[10px] font-mono text-tertiary">
            <span>{fileName}</span>
            <span>Line {source.start_line ?? "1"}</span>
          </div>
          {source.function_name && (
            <div className="text-[11px] font-mono font-semibold text-foreground truncate bg-surface-raised p-1 rounded border border-border/30">
              <span className="text-primary">fn</span> {source.function_name}()
            </div>
          )}
          <div className="rounded bg-background p-1.5 border border-border font-mono text-[9px] text-muted-foreground/80 overflow-hidden text-left leading-relaxed">
            <span className="text-primary-hover">import</span> {"{ modules }"} <span className="text-primary-hover">from</span> <span className="text-success">"app"</span>;
            <br />
            <span className="text-tertiary">// Reference node scope</span>
            <br />
            {source.function_name ? `${source.function_name} { ... }` : "class IngestionRunner { ... }"}
          </div>
        </div>
        {/* Pointer tip */}
        <div className="absolute top-full left-1/2 -translate-x-1/2 -mt-1 w-2.5 h-2.5 rotate-45 border-r border-b border-border bg-surface" />
      </div>
    </div>
  );
}
