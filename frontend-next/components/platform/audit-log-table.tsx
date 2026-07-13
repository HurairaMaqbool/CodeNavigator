import { useState } from "react";
import type { AuditEvent } from "@/lib/types";
import { Button } from "@/components/ui/button";

function maskDetails(details: Record<string, any> | undefined): string {
  if (!details || Object.keys(details).length === 0) return "—";
  
  const masked = { ...details };
  if (typeof masked.repo_url === "string") {
    const url = masked.repo_url;
    try {
      const parsed = new URL(url);
      const parts = parsed.pathname.split("/").filter(Boolean);
      if (parts.length >= 2) {
        // e.g. /secret/private-repo -> /secret/*******
        parsed.pathname = `/${parts[0]}/*******`;
      } else {
        parsed.pathname = "/*******";
      }
      masked.repo_url = parsed.toString();
    } catch {
      masked.repo_url = "https://github.com/******";
    }
  }
  return JSON.stringify(masked);
}

export function AuditLogTable({ events }: { events: AuditEvent[] }) {
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 8;

  if (events.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No audit events yet. Actions like chat, ingest, and API key changes appear here.
      </p>
    );
  }

  // Deduplicate events by primary fields to prevent duplicate rows displaying twice
  const uniqueEvents = events.filter((ev, idx, self) => 
    self.findIndex(e => 
      e.timestamp === ev.timestamp && 
      e.action === ev.action && 
      e.actor === ev.actor && 
      e.resource_id === ev.resource_id && 
      JSON.stringify(e.details) === JSON.stringify(ev.details)
    ) === idx
  );

  const totalPages = Math.max(1, Math.ceil(uniqueEvents.length / itemsPerPage));
  const paginatedEvents = uniqueEvents.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  );

  return (
    <div className="space-y-2">
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Action</th>
              <th>Actor</th>
              <th>Resource</th>
              <th>Details</th>
              <th>Correlation</th>
            </tr>
          </thead>
          <tbody>
            {paginatedEvents.map((row, i) => (
              <tr key={`${row.timestamp}-${i}`}>
                <td className="font-mono text-xs whitespace-nowrap">
                  {row.timestamp ? new Date(row.timestamp).toLocaleString() : "—"}
                </td>
                <td>{row.action}</td>
                <td>{row.actor || "—"}</td>
                <td className="font-mono text-xs truncate max-w-[150px]">
                  {row.resource_type
                    ? `${row.resource_type}/${row.resource_id || ""}`
                    : "—"}
                </td>
                <td className="max-w-xs truncate font-mono text-xs text-muted-foreground">
                  {maskDetails(row.details)}
                </td>
                <td className="font-mono text-xs text-muted-foreground">
                  {row.correlation_id?.slice(0, 8) ?? "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between border border-border bg-surface-raised px-4 py-2 rounded-lg">
          <p className="text-xs text-muted-foreground">
            Showing {((currentPage - 1) * itemsPerPage) + 1} to {Math.min(currentPage * itemsPerPage, uniqueEvents.length)} of {uniqueEvents.length} events
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs px-2"
              disabled={currentPage === 1}
              onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs px-2"
              disabled={currentPage === totalPages}
              onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
