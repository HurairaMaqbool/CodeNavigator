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

/* ─ Quality-tier helpers (must match page.tsx thresholds) ─ */
function qualityTierLabel(score: number): string {
  if (score >= 0.85) return "Excellent";
  if (score >= 0.70) return "Good";
  if (score >= 0.50) return "Needs work";
  return "Poor";
}
function qualityTierColor(score: number): string {
  if (score >= 0.70) return "#84a97f"; // --primary / sage-moss
  if (score >= 0.50) return "#ecc94b"; // --warning / amber
  return "#f56565";                     // --destructive / brick-red
}

const THRESHOLD = 0.7;

const METRIC_DEFS: Record<string, string> = {
  "faithfulness": "Faithfulness: how well the answer is grounded in retrieved context.",
  "answer relevancy": "Answer Relevancy: how pertinent the generated response is to the query.",
  "context precision": "Context Precision: whether ground truth files rank high in retrieved chunks.",
  "context recall": "Context Recall: whether all necessary ground truth files were retrieved.",
  "answer correctness": "Answer Correctness: semantic similarity and factual overlap with ground truth.",
};

/* ── Warm-Neutral Palette (Stone & Moss System) ───────────────
   Success: Forest Green (#48bb78)
   Warning: Ochre Amber (#ecc94b)
   Destructive: Warm Muted Brick-Red (#f56565)
───────────────────────────────────────────────────────────── */
const COLOR_SUCCESS = "#48bb78";
const COLOR_WARNING = "#ecc94b";
const COLOR_DESTRUCTIVE = "#f56565";

function barColor(value: number): string {
  if (value >= 0.7) return COLOR_SUCCESS;
  if (value >= 0.5) return COLOR_WARNING;
  return COLOR_DESTRUCTIVE;
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
        background: "#2b2824",
        borderColor: "#3a3630",
        color: "#f2efe9",
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
        <p className="mt-1.5 text-[11px] text-[#9e988c] leading-normal max-w-[240px] border-t border-[#3a3630]/40 pt-1.5">
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

  /** Custom tick: metric name + tier label on separate lines */
  const CustomAxisTick = (props: any) => {
    const { x, y, payload } = props;
    const entry = data.find((d) => d.name === payload.value);
    const val = entry?.value ?? 0;
    const tier = qualityTierLabel(val);
    const tierColor = qualityTierColor(val);
    return (
      <g transform={`translate(${x},${y})`}>
        <text
          x={0}
          y={0}
          dy={12}
          textAnchor="middle"
          fill="#9e988c"
          fontSize={9}
          fontFamily="var(--font-mono, monospace)"
          transform="rotate(-15)"
        >
          {payload.value}
        </text>
        <text
          x={0}
          y={0}
          dy={26}
          textAnchor="middle"
          fill={tierColor}
          fontSize={8}
          fontFamily="var(--font-mono, monospace)"
          fontWeight={600}
          transform="rotate(-15)"
        >
          {tier}
        </text>
      </g>
    );
  };

  return (
    <div className="h-[240px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 24, right: 12, left: -8, bottom: 56 }}>
          <CartesianGrid
            strokeDasharray="3 3"
            stroke="#3a3630"
            strokeOpacity={0.5}
            vertical={false}
          />
          <XAxis
            dataKey="name"
            tick={<CustomAxisTick />}
            height={68}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            domain={[0, 1]}
            tick={{ fontSize: 10, fill: "#9e988c" }}
            ticks={[0, 0.25, 0.5, 0.7, 0.75, 1]}
            axisLine={false}
            tickLine={false}
          />
          {/* Threshold reference line */}
          <ReferenceLine
            y={THRESHOLD}
            stroke="#84a97f"
            strokeDasharray="5 3"
            strokeOpacity={0.7}
            strokeWidth={1.5}
            label={{
              value: "target",
              position: "insideTopRight",
              fontSize: 9,
              fill: "#84a97f",
              opacity: 0.9,
            }}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: "#36322d", opacity: 0.5 }} />
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
                fill: "#9e988c",
              }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
