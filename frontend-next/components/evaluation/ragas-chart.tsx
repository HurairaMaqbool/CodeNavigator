"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { RagasScores } from "@/lib/types";

const THRESHOLD = 0.7;

const METRIC_DEFS: Record<string, string> = {
  "faithfulness": "Faithfulness: how well the answer is grounded in retrieved context.",
  "answer relevancy": "Answer Relevancy: how pertinent the generated response is to the query.",
  "context precision": "Context Precision: whether ground truth files rank high in retrieved chunks.",
  "context recall": "Context Recall: whether all necessary ground truth files were retrieved.",
  "answer correctness": "Answer Correctness: semantic similarity and factual overlap with ground truth.",
};

// Color-code bars: below threshold = amber, above = violet primary
function barColor(value: number): string {
  if (value >= THRESHOLD) return "var(--primary)";
  if (value >= 0.5) return "#f59e0b"; // amber
  return "#ef4444"; // red
}

interface RagasTooltipPayload {
  name?: string;
  value?: number;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: RagasTooltipPayload[];
}

function CustomTooltip({ active, payload }: CustomTooltipProps) {
  if (!active || !payload?.length) return null;
  const item = payload[0];
  const val = item?.value ?? 0;
  const color = barColor(val);
  const nameLower = String(item?.name ?? "").toLowerCase();
  const definition = METRIC_DEFS[nameLower] || "";

  return (
    <div
      className="rounded-lg border px-3 py-2 text-xs shadow-lg"
      style={{
        background: "var(--surface-raised)",
        borderColor: "var(--border)",
        color: "var(--foreground)",
      }}
    >
      <p className="font-medium capitalize">{String(item?.name ?? "")}</p>
      <p className="mt-0.5 font-mono tabular-nums font-semibold" style={{ color }}>
        {val.toFixed(3)}
        {val < THRESHOLD && (
          <span className="ml-1.5 opacity-70 text-[10px]">↓ below target ({THRESHOLD})</span>
        )}
      </p>
      {definition && (
        <p className="mt-1.5 text-[11px] text-muted-foreground leading-normal max-w-[240px] border-t border-border/20 pt-1.5">
          {definition}
        </p>
      )}
    </div>
  );
}

export function RagasChart({ scores }: { scores: RagasScores }) {
  const data = Object.entries(scores)
    .filter(([, v]) => typeof v === "number")
    .map(([name, value]) => ({
      name: name.replace(/_/g, " "),
      rawName: name,
      value: Math.round((value as number) * 1000) / 1000,
    }));

  if (data.length === 0) return null;

  return (
    <div className="h-[220px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 24, right: 12, left: -8, bottom: 44 }}>
          <CartesianGrid
            strokeDasharray="3 3"
            stroke="var(--border)"
            strokeOpacity={0.4}
            vertical={false}
          />
          <XAxis
            dataKey="name"
            tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
            angle={-20}
            textAnchor="end"
            height={56}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            domain={[0, 1]}
            tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
            ticks={[0, 0.25, 0.5, 0.7, 0.75, 1]}
            axisLine={false}
            tickLine={false}
          />
          {/* Threshold reference line */}
          <ReferenceLine
            y={THRESHOLD}
            stroke="#8b7cf8"
            strokeDasharray="5 3"
            strokeOpacity={0.6}
            strokeWidth={1.5}
            label={{
              value: "target",
              position: "insideTopRight",
              fontSize: 9,
              fill: "var(--primary)",
              opacity: 0.8,
            }}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: "var(--surface-hover)", opacity: 0.5 }} />
          <Bar dataKey="value" radius={[4, 4, 0, 0]} maxBarSize={42}>
            {data.map((entry) => (
              <Cell key={entry.rawName} fill={barColor(entry.value)} fillOpacity={0.9} />
            ))}
            {/* Value labels above bars */}
            <LabelList
              dataKey="value"
              position="top"
              formatter={(v: any) =>
                typeof v === "number" ? v.toFixed(3) : String(v ?? "")
              }
              style={{
                fontSize: "9px",
                fontFamily: "var(--font-mono, monospace)",
                fill: "var(--muted-foreground)",
              }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
