import type { ChatSource } from "@/lib/types";
import { cn } from "@/lib/utils";

export function CitationChip({ source }: { source: ChatSource }) {
  const label = `${source.file_path}:${source.start_line}-${source.end_line}`;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border border-border bg-muted/50 px-2 py-0.5",
        "font-mono text-xs text-foreground",
      )}
      title={source.function_name || label}
    >
      {label}
    </span>
  );
}
