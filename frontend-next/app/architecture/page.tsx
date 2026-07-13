"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, GitBranchPlus, Loader2, Network } from "lucide-react";
import { toast } from "sonner";
import { AppShell } from "@/components/layout/app-shell";
import { PanelErrorBoundary } from "@/components/shared/error-boundary";
import { SectionHeader } from "@/components/shared/section-header";
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

export default function ArchitecturePage() {
  const router = useRouter();
  const { repoId, clearSession } = useApp();
  const status = useRepoStatus(repoId);
  const ready = status.data ? repoIsReady(status.data) : false;
  const handleQuickStart = useIngestFlow();

  // Settings states
  const [selectedSymbol, setSelectedSymbol] = useState<SymbolItem | null>(null);
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
    // Determine details
    setInspectedSymbol(nodeLabel);
    setInspectedPath(selectedSymbol?.path || "src/requests/models.py");
    setInspectedType("method");
    setInspectedStartLine(selectedSymbol?.start_line || 1);
    setInspectedEndLine(selectedSymbol?.end_line || 100);
  };

  if (!repoId || status.isLoading || !ready) {
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
      <div className="page-enter space-y-8">
        {/* Section Header */}
        <div className="flex flex-wrap items-end justify-between gap-4">
          <SectionHeader
            title="Architecture Explorer"
            caption="Explore interactive call-graphs, trace callers/callees, visual circular dependencies, and perform side-by-side version diff comparisons."
            className="mb-0"
          />
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

        {/* Control Controls Panel */}
        <div className="card-panel grid gap-6 md:grid-cols-4 items-end">
          <div className="md:col-span-2 space-y-2">
            <Label htmlFor="search-symbol">Search Symbol</Label>
            <SymbolSearchBar
              repoId={repoId}
              onSelectSymbol={(sym) => {
                setSelectedSymbol(sym);
                setInspectedSymbol(null); // Reset detail panel
              }}
              disabled={loading}
            />
          </div>

          <div className="space-y-2">
            <Label>Direction</Label>
            <Select
              value={direction}
              onValueChange={(v) => setDirection(v as Direction)}
              disabled={loading}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select Direction" />
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
              disabled={loading}
            />
          </div>
        </div>

        {/* Feature Toggles */}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            {/* Granularity Toggle */}
            <div className="flex items-center gap-1.5 rounded-lg border border-border bg-surface px-2 py-1 shadow-sm text-xs">
              <span className="text-muted-foreground font-semibold px-1.5">Granularity:</span>
              <button
                type="button"
                className={`px-2 py-1 rounded transition-colors ${
                  granularity === "function"
                    ? "bg-primary text-primary-foreground font-semibold"
                    : "text-muted-foreground hover:text-foreground"
                }`}
                onClick={() => setGranularity("function")}
              >
                Function
              </button>
              <button
                type="button"
                className={`px-2 py-1 rounded transition-colors ${
                  granularity === "file"
                    ? "bg-primary text-primary-foreground font-semibold"
                    : "text-muted-foreground hover:text-foreground"
                }`}
                onClick={() => setGranularity("file")}
              >
                File
              </button>
            </div>

            {/* Diff Mode Toggle */}
            <div className="flex items-center gap-1.5 rounded-lg border border-border bg-surface px-2 py-1 shadow-sm text-xs">
              <span className="text-muted-foreground font-semibold px-1.5">Diff Mode:</span>
              <button
                type="button"
                className={`px-2 py-1 rounded transition-colors ${
                  !diffMode
                    ? "bg-primary text-primary-foreground font-semibold"
                    : "text-muted-foreground hover:text-foreground"
                }`}
                onClick={() => setDiffMode(false)}
              >
                Off
              </button>
              <button
                type="button"
                className={`px-2 py-1 rounded transition-colors ${
                  diffMode
                    ? "bg-primary text-primary-foreground font-semibold"
                    : "text-muted-foreground hover:text-foreground"
                }`}
                onClick={() => setDiffMode(true)}
              >
                On
              </button>
            </div>
          </div>

          {diffMode && (
            <div className="flex items-center gap-2">
              <Label className="text-xs text-muted-foreground whitespace-nowrap">Compare Commit:</Label>
              <Select
                value={candidateRepoId}
                onValueChange={setCandidateRepoId}
              >
                <SelectTrigger className="w-[180px] h-8 text-xs">
                  <SelectValue placeholder="Select Version" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={repoId}>Same Commit (Baseline)</SelectItem>
                  {/* Fallback option for testing/demo */}
                  <SelectItem value="375c63667dff3e1e20ef5712cf1c0cb33940a9b49644bb855f1f89fe959d9f4d">
                    Version 2.0 (Candidate)
                  </SelectItem>
                </SelectContent>
              </Select>
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
                      <div className="h-[580px] rounded-lg border border-border bg-surface-raised flex flex-col items-center justify-center p-8 text-center text-muted-foreground">
                        <Network className="h-10 w-10 mb-3 text-primary animate-pulse" />
                        <p className="font-semibold text-foreground text-xs mb-1">Select a symbol to begin</p>
                      </div>
                    ) : mermaid ? (
                      <DiagramCanvas
                        markdown={mermaid}
                        symbolName={selectedSymbol?.name || "diagram"}
                        onNodeClick={handleNodeClick}
                      />
                    ) : (
                      <div className="h-[580px] rounded-lg border border-border bg-surface-raised flex flex-col items-center justify-center p-8 text-center text-muted-foreground">
                        <Network className="h-10 w-10 mb-3 text-muted/60" />
                        <p className="font-semibold text-foreground">No call graph found</p>
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
                      <div className="h-[580px] rounded-lg border border-border bg-surface-raised flex flex-col items-center justify-center p-8 text-center text-muted-foreground">
                        <Network className="h-10 w-10 mb-3 text-primary animate-pulse" />
                        <p className="font-semibold text-foreground text-xs mb-1">Select a symbol to begin</p>
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
                      <div className="h-[580px] rounded-lg border border-border bg-surface-raised flex flex-col items-center justify-center p-8 text-center text-muted-foreground">
                        <Network className="h-10 w-10 mb-3 text-muted/60" />
                        <p className="font-semibold text-foreground">Select candidate commit to compare</p>
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
                  <div className="h-[580px] rounded-lg border border-border bg-surface-raised flex flex-col items-center justify-center p-8 text-center text-muted-foreground">
                    <Network className="h-12 w-12 mb-4 text-primary animate-pulse" />
                    <p className="font-semibold text-foreground text-base mb-1">Select a symbol to visualize its call graph</p>
                    <p className="text-xs text-muted-foreground max-w-sm">Use the Go to Symbol search bar above to fuzzy search functions, classes, or methods and explore their relationship dependencies.</p>
                  </div>
                ) : mermaid ? (
                  <DiagramCanvas
                    markdown={mermaid}
                    symbolName={selectedSymbol?.name || "diagram"}
                    onNodeClick={handleNodeClick}
                  />
                ) : (
                  <div className="h-[580px] rounded-lg border border-border bg-surface-raised flex flex-col items-center justify-center p-8 text-center text-muted-foreground">
                    <Network className="h-10 w-10 mb-3 text-muted/60" />
                    <p className="font-semibold text-foreground">No call graph found</p>
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
