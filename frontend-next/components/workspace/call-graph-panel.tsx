"use client";

import { useState } from "react";
import { GitBranch, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { getDiagram } from "@/lib/api";
import { useApp } from "@/lib/context/app-context";
import { ApiError } from "@/lib/types";
import { PanelErrorBoundary } from "@/components/shared/error-boundary";
import { SectionHeader } from "@/components/shared/section-header";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { MermaidViewer } from "./mermaid-viewer";

type CallGraphPanelProps = {
  repoId: string;
  ready: boolean;
};

export function CallGraphPanel({ repoId, ready }: CallGraphPanelProps) {
  const { lastDiagramSymbol, setLastDiagramSymbol } = useApp();
  const [symbol, setSymbol] = useState(lastDiagramSymbol ?? "Session.send");
  const [depth, setDepth] = useState(2);
  const [mermaid, setMermaid] = useState<string | null>(null);
  const [clamped, setClamped] = useState(false);
  const [empty, setEmpty] = useState(false);
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
    try {
      const res = await getDiagram(repoId, fn, depth);
      setLastDiagramSymbol(fn);
      setClamped(res.clamped);
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
    <div className="rounded-xl border border-border bg-surface p-5 shadow-sm">
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
