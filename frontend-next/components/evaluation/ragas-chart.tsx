"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { RagasScores } from "@/lib/types";

export function RagasChart({ scores }: { scores: RagasScores }) {
  const data = Object.entries(scores).map(([name, value]) => ({
    name: name.replace(/_/g, " "),
    value: Math.round(value * 1000) / 1000,
  }));

  if (data.length === 0) return null;

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 40 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
          <XAxis
            dataKey="name"
            tick={{ fontSize: 11 }}
            angle={-25}
            textAnchor="end"
            height={60}
          />
          <YAxis domain={[0, 1]} tick={{ fontSize: 11 }} />
          <Tooltip />
          <Bar dataKey="value" fill="#6366f1" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
