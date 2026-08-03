"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, GitBranchPlus, Loader2, Network } from "lucide-react";
import { toast } from "sonner";
import { AppShell } from "@/components/layout/app-shell";
import { PanelErrorBoundary } from "@/components/shared/error-boundary";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { ScreenSkeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SymbolSearchBar } from "@/components/workspace/symbol-search-bar";
import { DiagramCanvas } from "@/components/workspace/diagram-canvas";
import { NodeDetailPanel } from "@/components/workspace/node-detail-panel";
import { getDiagram, type SymbolItem } from "@/lib/api";
import { useApp } from "@/lib/context/app-context";
import { repoIsReady } from "@/lib/constants";
import { useIngestFlow } from "@/lib/hooks/use-ingest-flow";
import { useRepoStatus } from "@/lib/hooks/use-repo-status";
import { ApiError } from "@/lib/types";

type Direction = "downstream" | "upstream" | "both";

const DEFAULT_SYMBOL: SymbolItem = {
  id: "run",
  name: "run",
  path: "app/agent/loop.py",
  type: "function",
  start_line: 50,
  end_line: 120,
};

export default function ArchitecturePage() {
  const router = useRouter();
  const { repoId, clearSession } = useApp();
  const status = useRepoStatus(repoId);
  const ready = status.data ? repoIsReady(status.data) : false;
  const handleQuickStart = useIngestFlow();

  // Settings states
  const [selectedSymbol, setSelectedSymbol] = useState<SymbolItem | null>(DEFAULT_SYMBOL);
  const [depth, setDepth] = useState(2);
  const [direction, setDirection] = useState<Direction>("downstream");
  const [granularity, setGranularity] = useState<"function" | "file">("function");

  // Diagram rendering states
  const [loading, setLoading] = useState(false);
  const [mermaid, setMermaid] = useState<string | null>(null);
  const [clamped, setClamped] = useState(false);

  // Inspector panel states
  const [inspectedSymbol, setInspectedSymbol] = useState<string | null>(null);
  const [inspectedPath, setInspectedPath] = useState<string | null>(null);
  const [inspectedType, setInspectedType] = useState<string | null>(null);
  const [inspectedStartLine, setInspectedStartLine] = useState<number | null>(null);
  const [inspectedEndLine, setInspectedEndLine] = useState<number | null>(null);

  // Diff Mode states
  const [diffMode, setDiffMode] = useState(false);
  const [candidateRepoId, setCandidateRepoId] = useState("");
  const [candidateMermaid, setCandidateMermaid] = useState<string | null>(null);
  const [candidateLoading, setCandidateLoading] = useState(false);
  const [candidateError, setCandidateError] = useState<string | null>(null);

  useEffect(() => {
    if (!repoId) {
      router.replace("/onboarding");
      return;
    }
    if (!status.isLoading && status.data && !repoIsReady(status.data)) {
      router.replace("/onboarding");
    }
  }, [repoId, status.isLoading, status.data, router]);

  // Fetch diagram from API
  async function generate(symName: string) {
    if (!repoId || !symName) return;
    setLoading(true);
    setMermaid(null);
    try {
      const res = await getDiagram(repoId, symName, depth, direction);
      setClamped(res.clamped);
      
      let diagramMarkdown = res.mermaid;
      
      // If File-level granularity toggle is active, group nodes by path client-side
      if (granularity === "file" && res.mermaid) {
        diagramMarkdown = convertToOverviewDiagram(res.mermaid);
      }
      
      setMermaid(diagramMarkdown);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Diagram generation failed");
    } finally {
      setLoading(false);
    }
  }

  // Generate Candidate Diagram (Diff Mode)
  async function generateCandidate(symName: string, candId: string) {
    if (!candId || !symName) return;
    setCandidateLoading(true);
    setCandidateMermaid(null);
    setCandidateError(null);
    try {
      const res = await getDiagram(candId, symName, depth, direction);
      let diagramMarkdown = res.mermaid;
      if (granularity === "file" && res.mermaid) {
        diagramMarkdown = convertToOverviewDiagram(res.mermaid);
      }
      setCandidateMermaid(diagramMarkdown);
    } catch (e) {
      const errorMsg = e instanceof ApiError ? e.message : "Candidate diagram failed";
      setCandidateError(errorMsg);
      toast.error(errorMsg);
    } finally {
      setCandidateLoading(false);
    }
  }

  // Trigger regeneration on parameter changes
  useEffect(() => {
    if (ready && selectedSymbol) {
      void generate(selectedSymbol.name);
      if (diffMode && candidateRepoId) {
        void generateCandidate(selectedSymbol.name, candidateRepoId);
      }
    }
  }, [ready, selectedSymbol?.name, depth, direction, granularity]);

  // When Diff Mode is toggled, generate candidate diagram if candidateRepoId is selected
  useEffect(() => {
    if (diffMode && selectedSymbol && candidateRepoId) {
      void generateCandidate(selectedSymbol.name, candidateRepoId);
    } else {
      setCandidateMermaid(null);
      setCandidateError(null);
    }
  }, [diffMode, candidateRepoId]);

  // Client-side parser to translate Function-level Mermaid into File-level diagram
  function convertToOverviewDiagram(rawMermaid: string): string {
    const lines = rawMermaid.split("\n");
    const header = lines[0] || "graph TD";
    const filesSeen = new Set<string>();
    const fileEdges = new Set<string>();

    const nodeLabelMap: Record<string, string> = {};

    // 1. First pass: map node IDs to file paths
    lines.forEach((line) => {
      const nodeRegex = /([a-zA-Z0-9_]+)\["([^"]+)"\]/g;
      let match;
      while ((match = nodeRegex.exec(line)) !== null) {
        const nid = match[1];
        const label = match[2];
        if (nid && label) {
          const parts = label.split(":");
          let path = label;
          if (parts.length > 1) {
            if (parts[0].length === 1 && (parts[1].startsWith("\\") || parts[1].startsWith("/"))) {
              // Windows absolute path: join drive letter (e.g., D:\path)
              path = `${parts[0]}:${parts[1]}`.trim();
            } else {
              path = parts[0].trim();
            }
          }
          nodeLabelMap[nid] = path;
          filesSeen.add(path);
        }
      }
    });

    // 2. Second pass: map edges between files
    lines.forEach((line) => {
      const edgeMatch = /([a-zA-Z0-9_]+)\s*(?:-->|-.->\|cycle\|)\s*([a-zA-Z0-9_]+)/.exec(line);
      if (edgeMatch) {
        const srcNid = edgeMatch[1];
        const tgtNid = edgeMatch[2];
        if (srcNid && tgtNid) {
          const srcFile = nodeLabelMap[srcNid];
          const tgtFile = nodeLabelMap[tgtNid];
          if (srcFile && tgtFile && srcFile !== tgtFile) {
            fileEdges.add(`${srcFile} --> ${tgtFile}`);
          }
        }
      }
    });

    // 3. Rebuild Mermaid markdown
    const fileLines = [header];
    let fileIdCounter = 1;
    const fileToIdMap: Record<string, string> = {};

    filesSeen.forEach((file) => {
      const fid = `f_${fileIdCounter++}`;
      fileToIdMap[file] = fid;
      fileLines.push(`    ${fid}["${file}"]`);
    });

    fileEdges.forEach((edge) => {
      const parts = edge.split(" --> ");
      const src = parts[0];
      const tgt = parts[1];
      if (src && tgt) {
        const srcFid = fileToIdMap[src];
        const tgtFid = fileToIdMap[tgt];
        if (srcFid && tgtFid) {
          fileLines.push(`    ${srcFid} --> ${tgtFid}`);
        }
      }
    });

    if (fileLines.length <= 1) {
      return `${header}\n    no_file_connections["No file-level connections found"]`;
    }

    return fileLines.join("\n");
  }

  // Handle clicking on a node in the diagram canvas
  const handleNodeClick = (nodeLabel: string) => {
    let parsedPath = selectedSymbol?.path || null;
    let parsedSymbol = nodeLabel;
    let parsedLine: number | null = null;

    if (nodeLabel.includes(":")) {
      const parts = nodeLabel.split(":");
      if (parts.length > 2 && parts[0].length === 1) {
        parsedPath = `${parts[0]}:${parts[1]}`;
        parsedSymbol = parts.slice(2).join(":");
      } else {
        parsedPath = parts[0];
        parsedSymbol = parts.slice(1).join(":");
      }
      if (/^\d+$/.test(parsedSymbol)) {
        parsedLine = parseInt(parsedSymbol, 10);
      }
    }

    setInspectedSymbol(parsedSymbol || nodeLabel);
    setInspectedPath(parsedPath);
    setInspectedType("method");
    setInspectedStartLine(parsedLine ?? selectedSymbol?.start_line ?? null);
    setInspectedEndLine(parsedLine ? parsedLine + 30 : selectedSymbol?.end_line ?? null);
  };

  if (!repoId) {
    return (
      <AppShell onQuickStart={(url, ref) => void handleQuickStart(url, ref)}>
        <div className="page-enter">
          <ScreenSkeleton cards={2} />
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell onQuickStart={(url, ref) => void handleQuickStart(url, ref)}>
      <div className="page-enter space-y-6">
        {/* ─── Breadcrumb Bar ────────────────────────── */}
        <div className="flex items-center gap-2 text-xs text-muted-foreground font-mono select-none">
          <span>Workspace</span>
          <span className="text-border-strong">/</span>
          <span className="text-foreground font-medium">{(status.data?.repo_id || repoId).slice(0, 16)}</span>
          <span className="text-border-strong">/</span>
          <span>architecture</span>
          <span className="text-border-strong">/</span>
          <span className="text-primary font-semibold truncate max-w-[200px]">
            {selectedSymbol?.name || "Call Graph"}
          </span>
        </div>

        {/* ─── Header Row ───────────────────────────── */}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="font-display text-2xl font-bold tracking-tight text-foreground">
              Architecture Explorer
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Call-graph inspection · callers / callees · cycle detection
            </p>
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              clearSession();
              router.push("/onboarding");
            }}
          >
            <GitBranchPlus className="h-4 w-4" />
            New repository
          </Button>
        </div>

        {/* ─── Toolbar ──────────────────────────────── */}
        <div className="card-panel space-y-4">
          {/* Row 1: Symbol search + Direction + Depth chip */}
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex-1 min-w-[200px] space-y-1.5">
              <Label htmlFor="search-symbol" className="text-xs text-muted-foreground">Symbol</Label>
              <SymbolSearchBar
                repoId={repoId}
                onSelectSymbol={(sym) => {
                  setSelectedSymbol(sym);
                  setInspectedSymbol(null);
                }}
                disabled={loading}
              />
            </div>

            <div className="w-44 space-y-1.5">
              <Label className="text-xs text-muted-foreground">Direction</Label>
              <Select
                value={direction}
                onValueChange={(v) => setDirection(v as Direction)}
                disabled={loading}
              >
                <SelectTrigger className="h-9 text-xs">
                  <SelectValue placeholder="Direction" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="downstream">Callees (downstream)</SelectItem>
                  <SelectItem value="upstream">Callers (upstream)</SelectItem>
                  <SelectItem value="both">Both directions</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Depth chip */}
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Depth</Label>
              <div className="flex items-center gap-2">
                <span className="inline-flex h-9 items-center rounded-lg border border-border bg-surface-elevated px-3 font-mono text-sm text-foreground">
                  {depth}
                </span>
                <div className="w-28">
                  <Slider
                    min={1}
                    max={5}
                    step={1}
                    value={[depth]}
                    onValueChange={(v) => setDepth(v[0] ?? 2)}
                    disabled={loading}
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Row 2: Segmented toggles + filter pills */}
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border/30 pt-3">
            <div className="flex items-center gap-3">
              {/* Granularity segmented control */}
              <div className="inline-flex items-center rounded-lg bg-surface p-1 border border-border/60">
                {(["function", "file"] as const).map((g) => (
                  <button
                    key={g}
                    type="button"
                    disabled={loading}
                    onClick={() => setGranularity(g)}
                    className={`rounded-md px-3 py-1 text-xs font-medium capitalize transition-all duration-150 ${
                      granularity === g
                        ? "bg-accent text-primary shadow-sm"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {g}
                  </button>
                ))}
              </div>

              {/* Diff Mode segmented control */}
              <div className="inline-flex items-center rounded-lg bg-surface p-1 border border-border/60">
                {([false, true] as const).map((mode) => (
                  <button
                    key={String(mode)}
                    type="button"
                    disabled={loading}
                    onClick={() => setDiffMode(mode)}
                    className={`rounded-md px-3 py-1 text-xs font-medium transition-all duration-150 ${
                      diffMode === mode
                        ? "bg-accent text-primary shadow-sm"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {mode ? "Diff" : "Normal"}
                  </button>
                ))}
              </div>
            </div>

            {/* Filter pills */}
            <div className="flex items-center gap-2">
              <span className="text-[10px] uppercase tracking-widest text-muted-foreground">Filter:</span>
              {["Cycles only", "Entry points", "Exports"].map((pill) => (
                <button
                  key={pill}
                  type="button"
                  className="rounded-full border border-border/60 px-2.5 py-0.5 text-[11px] text-muted-foreground transition-all duration-150 hover:border-primary/40 hover:bg-accent hover:text-primary"
                >
                  {pill}
                </button>
              ))}
            </div>
          </div>

          {/* Diff mode: compare commit selector (shown inside toolbar) */}
          {diffMode && (
            <div className="border-t border-border/30 pt-3">
              <div className="flex items-center gap-3">
                <Label className="text-xs text-muted-foreground whitespace-nowrap">Compare commit:</Label>
                <Select value={candidateRepoId} onValueChange={setCandidateRepoId}>
                  <SelectTrigger className="w-56 h-9 text-xs">
                    <SelectValue placeholder="Select Version" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={repoId}>Same Commit (Baseline)</SelectItem>
                    <SelectItem value="375c63667dff3e1e20ef5712cf1c0cb33940a9b49644bb855f1f89fe959d9f4d">
                      Version 2.0 (Candidate)
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}
        </div>


        {/* Graph Explorer Canvas Grid */}
        <div className="grid gap-6 lg:grid-cols-3">
          {/* Canvas Display */}
          <div className="lg:col-span-2 space-y-4">
            {diffMode ? (
              <div className="grid gap-4 md:grid-cols-2">
                {/* Baseline Canvas */}
                <div className="space-y-2">
                  <span className="inline-flex items-center rounded-md bg-muted px-2 py-0.5 text-xs font-medium text-foreground">
                    Baseline (Original)
                  </span>
                  <PanelErrorBoundary title="Baseline canvas error">
                    {loading ? (
                      <div className="h-[580px] rounded-lg border border-border bg-surface-raised flex items-center justify-center">
                        <Loader2 className="h-6 w-6 animate-spin text-primary" />
                      </div>
                    ) : selectedSymbol === null ? (
                      <div className="h-[580px] rounded-lg border border-border bg-surface-raised flex flex-col items-center justify-center p-8 text-center text-muted-foreground dot-grid relative">
                        <p className="font-semibold text-foreground text-xs mb-1 font-display">Select a symbol to begin</p>
                      </div>
                    ) : mermaid ? (
                      <DiagramCanvas
                        markdown={mermaid}
                        symbolName={selectedSymbol?.name || "diagram"}
                        onNodeClick={handleNodeClick}
                      />
                    ) : (
                      <div className="h-[580px] rounded-lg border border-border bg-surface-raised flex flex-col items-center justify-center p-8 text-center text-muted-foreground dot-grid relative">
                        <p className="font-semibold text-foreground font-display">No call graph found</p>
                      </div>
                    )}
                  </PanelErrorBoundary>
                </div>

                {/* Candidate Canvas */}
                <div className="space-y-2">
                  <span className="inline-flex items-center rounded-md bg-warning/20 px-2 py-0.5 text-xs font-medium text-warning">
                    Candidate (Compare)
                  </span>
                  <PanelErrorBoundary title="Candidate canvas error">
                    {candidateLoading ? (
                      <div className="h-[580px] rounded-lg border border-border bg-surface-raised flex items-center justify-center">
                        <Loader2 className="h-6 w-6 animate-spin text-primary" />
                      </div>
                    ) : selectedSymbol === null ? (
                      <div className="h-[580px] rounded-lg border border-border bg-surface-raised flex flex-col items-center justify-center p-8 text-center text-muted-foreground dot-grid relative">
                        <p className="font-semibold text-foreground text-xs mb-1 font-display">Select a symbol to begin</p>
                      </div>
                    ) : candidateError ? (
                      <div className="h-[580px] rounded-lg border border-border bg-surface-raised flex flex-col items-center justify-center p-8 text-center text-warning">
                        <AlertTriangle className="h-8 w-8 mb-2" />
                        <p className="font-semibold">Cannot match symbol across versions</p>
                        <p className="text-xs text-muted-foreground mt-1">{candidateError}</p>
                      </div>
                    ) : candidateMermaid ? (
                      <DiagramCanvas
                        markdown={candidateMermaid}
                        symbolName={selectedSymbol?.name || "diagram"}
                        onNodeClick={handleNodeClick}
                      />
                    ) : (
                      <div className="h-[580px] rounded-lg border border-border bg-surface-raised flex flex-col items-center justify-center p-8 text-center text-muted-foreground dot-grid relative">
                        <p className="font-semibold text-foreground font-display">Select candidate commit to compare</p>
                      </div>
                    )}
                  </PanelErrorBoundary>
                </div>
              </div>
            ) : (
              /* Single Mode Canvas */
              <PanelErrorBoundary title="Call graph explorer error">
                {loading ? (
                  <div className="h-[580px] rounded-lg border border-border bg-surface-raised flex items-center justify-center">
                    <Loader2 className="h-6 w-6 animate-spin text-primary" />
                  </div>
                ) : selectedSymbol === null ? (
                  <div className="h-[580px] rounded-lg border border-border bg-surface-raised flex flex-col items-center justify-center p-8 text-center text-muted-foreground dot-grid relative overflow-hidden group">
                    <div className="absolute inset-0 bg-gradient-to-t from-background/80 via-transparent to-transparent pointer-events-none" />
                    <div className="mb-6 flex h-20 w-20 items-center justify-center rounded-2xl border border-border bg-surface shadow-elev-1 relative z-10">
                      <svg className="h-10 w-10 text-primary animate-pulse" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <circle cx="20" cy="8" r="4" stroke="currentColor" strokeWidth="1.5" />
                        <circle cx="10" cy="24" r="4" stroke="currentColor" strokeWidth="1.5" />
                        <circle cx="30" cy="24" r="4" stroke="currentColor" strokeWidth="1.5" />
                        <path d="M18 11.5L12 20.5" stroke="currentColor" strokeWidth="1.5" strokeDasharray="2 2" />
                        <path d="M22 11.5L28 20.5" stroke="currentColor" strokeWidth="1.5" strokeDasharray="2 2" />
                        <path d="M14 24H26" stroke="currentColor" strokeWidth="1.5" />
                      </svg>
                    </div>
                    <p className="font-semibold text-foreground text-base mb-1 relative z-10 font-display">Select a symbol to visualize its call graph</p>
                    <p className="text-xs text-muted-foreground max-w-sm relative z-10 leading-relaxed">Use the Go to Symbol search bar above to fuzzy search functions, classes, or methods and explore their relationship dependencies.</p>
                  </div>
                ) : mermaid ? (
                  <DiagramCanvas
                    markdown={mermaid}
                    symbolName={selectedSymbol?.name || "diagram"}
                    onNodeClick={handleNodeClick}
                  />
                ) : (
                  <div className="h-[580px] rounded-lg border border-border bg-surface-raised flex flex-col items-center justify-center p-8 text-center text-muted-foreground dot-grid relative">
                    <div className="mb-6 flex h-20 w-20 items-center justify-center rounded-2xl border border-border bg-surface shadow-elev-1">
                      <svg className="h-10 w-10 text-muted-foreground" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <circle cx="20" cy="20" r="10" stroke="currentColor" strokeWidth="1.5" strokeDasharray="3 3" />
                        <line x1="20" y1="10" x2="20" y2="30" stroke="currentColor" strokeWidth="1.5" />
                      </svg>
                    </div>
                    <p className="font-semibold text-foreground font-display">No call graph found</p>
                  </div>
                )}
              </PanelErrorBoundary>
            )}
          </div>

          {/* Details Inspector Side-Panel */}
          <div>
            <PanelErrorBoundary title="Inspector error">
              <NodeDetailPanel
                repoId={repoId}
                symbolName={inspectedSymbol}
                filePath={inspectedPath}
                type={inspectedType}
                startLine={inspectedStartLine}
                endLine={inspectedEndLine}
                onClose={() => setInspectedSymbol(null)}
              />
            </PanelErrorBoundary>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
