"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, GitBranch, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { getDiagram } from "@/lib/api";
import { useApp } from "@/lib/context/app-context";
import { ApiError, type HiddenNeighbor } from "@/lib/types";
import { PanelErrorBoundary } from "@/components/shared/error-boundary";
import { SectionHeader } from "@/components/shared/section-header";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { MermaidViewer } from "./mermaid-viewer";

type CallGraphPanelProps = {
  repoId: string;
  ready: boolean;
};

type Direction = "downstream" | "upstream" | "both";

export function CallGraphPanel({ repoId, ready }: CallGraphPanelProps) {
  const { lastDiagramSymbol, setLastDiagramSymbol } = useApp();
  const [symbol, setSymbol] = useState(lastDiagramSymbol ?? "Session.send");
  const [depth, setDepth] = useState(2);
  const [direction, setDirection] = useState<Direction>("downstream");
  const [mermaid, setMermaid] = useState<string | null>(null);
  const [clamped, setClamped] = useState(false);
  const [empty, setEmpty] = useState(false);
  const [hiddenNeighbors, setHiddenNeighbors] = useState<HiddenNeighbor[]>([]);
  const [truncatedCount, setTruncatedCount] = useState(0);
  const [showHidden, setShowHidden] = useState(false);
  const [loading, setLoading] = useState(false);

  async function generate() {
    const fn = symbol.trim();
    if (!fn) {
      toast.info("Enter a symbol name (e.g. Session.send)");
      return;
    }
    setLoading(true);
    setMermaid(null);
    setEmpty(false);
    setHiddenNeighbors([]);
    setTruncatedCount(0);
    setShowHidden(false);
    try {
      const res = await getDiagram(repoId, fn, depth, direction);
      setLastDiagramSymbol(fn);
      setClamped(res.clamped);
      setHiddenNeighbors(res.hidden_neighbors ?? []);
      setTruncatedCount(res.truncated_count ?? res.hidden_count ?? 0);
      if (res.empty || !res.mermaid) {
        setEmpty(true);
      } else {
        setMermaid(res.mermaid);
      }
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Diagram failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card-panel">
      <SectionHeader title="Call graph" caption="Mermaid diagram for a symbol" />

      {!ready && (
        <Alert kind="info" className="mb-4">
          Indexing must finish before generating diagrams.
        </Alert>
      )}

      <div className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="symbol">Symbol</Label>
          <Input
            id="symbol"
            placeholder="Session.send"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            disabled={!ready || loading}
          />
        </div>
        <div className="space-y-2">
          <Label>Direction</Label>
          <Select
            value={direction}
            onValueChange={(v) => setDirection(v as Direction)}
            disabled={!ready || loading}
          >
            <SelectTrigger>
              <SelectValue placeholder="Traversal direction" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="downstream">Callees (downstream)</SelectItem>
              <SelectItem value="upstream">Callers (upstream)</SelectItem>
              <SelectItem value="both">Both directions</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label>Depth: {depth}</Label>
          <Slider
            min={1}
            max={5}
            step={1}
            value={[depth]}
            onValueChange={(v) => setDepth(v[0] ?? 2)}
            disabled={!ready || loading}
          />
        </div>
        <Button
          variant="secondary"
          className="w-full"
          disabled={!ready || loading}
          onClick={() => void generate()}
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <GitBranch className="h-4 w-4" />
          )}
          Generate diagram
        </Button>

        {clamped && (
          <p className="text-xs text-muted-foreground">
            Depth was clamped to keep the graph readable.
          </p>
        )}

        {truncatedCount > 0 && (
          <div className="rounded-lg border border-border bg-muted/30 p-3 text-sm">
            <button
              type="button"
              className="flex w-full items-center gap-2 text-left font-medium text-foreground"
              onClick={() => setShowHidden((v) => !v)}
            >
              {showHidden ? (
                <ChevronDown className="h-4 w-4 shrink-0" />
              ) : (
                <ChevronRight className="h-4 w-4 shrink-0" />
              )}
              +{truncatedCount} more relationships not shown
            </button>
            {showHidden && hiddenNeighbors.length > 0 && (
              <ul className="mt-2 max-h-48 space-y-1 overflow-auto text-xs text-muted-foreground">
                {hiddenNeighbors.map((n, index) => (
                  <li
                    key={`${n.parent_id}|${n.id}|${n.direction}|${index}`}
                  >
                    <span className="font-medium text-foreground">{n.name}</span>
                    {n.path ? ` · ${n.path}` : ""}
                    <span className="ml-1 text-muted-foreground">
                      ({n.direction === "caller" ? "calls" : "called from"}{" "}
                      {n.parent_name})
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {showHidden && hiddenNeighbors.length === 0 && (
              <p className="mt-2 text-xs text-muted-foreground">
                Additional neighbors were omitted to keep the diagram readable.
                Try callers-only or callees-only for hub symbols.
              </p>
            )}
          </div>
        )}

        {empty && (
          <p className="text-sm text-muted-foreground">
            No graph found for this symbol.
          </p>
        )}

        {mermaid && (
          <PanelErrorBoundary title="Diagram viewer crashed">
            <MermaidViewer markdown={mermaid} />
          </PanelErrorBoundary>
        )}
      </div>
    </div>
  );
}
