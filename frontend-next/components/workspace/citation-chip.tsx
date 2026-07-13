import type { ChatSource } from "@/lib/types";
import { cn } from "@/lib/utils";

export function CitationChip({ source }: { source: ChatSource }) {
  const linesLabel = source.lines 
    ? `:${source.lines}` 
    : source.start_line != null 
      ? `:${source.start_line}-${source.end_line}` 
      : "";
  const label = `${source.file_path}${linesLabel}`;

  return (
    <span
      className={cn(
        "inline-flex max-w-full items-center truncate rounded-md border border-border",
        "bg-surface-raised/50 px-2 py-0.5 font-mono text-[11px] text-muted-foreground select-all",
        "transition-all duration-150 hover:border-primary/30 hover:bg-primary/5 hover:text-primary cursor-help",
      )}
      title={source.function_name ? `${source.function_name} · ${label}` : label}
    >
      {label}
    </span>
  );
}
