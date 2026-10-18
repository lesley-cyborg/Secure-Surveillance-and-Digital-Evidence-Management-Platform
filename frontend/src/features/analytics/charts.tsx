"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { DayPoint, NamedCount } from "./aggregate";

const COLORS = [
  "#38bdf8",
  "#34d399",
  "#fbbf24",
  "#f87171",
  "#a78bfa",
  "#fb7185",
  "#2dd4bf",
  "#94a3b8",
];

export function TrendBarChart({ data }: { data: DayPoint[] }) {
  const empty = data.every((d) => d.count === 0);
  if (empty) {
    return (
      <p className="flex h-48 items-center justify-center text-sm text-zinc-500">
        No incidents in this range
      </p>
    );
  }
  return (
    <div className="h-48 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#3f3f46" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fill: "#a1a1aa", fontSize: 10 }}
            axisLine={{ stroke: "#3f3f46" }}
            tickLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            allowDecimals={false}
            tick={{ fill: "#a1a1aa", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{
              background: "#18181b",
              border: "1px solid #3f3f46",
              borderRadius: 8,
              fontSize: 12,
            }}
            labelFormatter={(_, p) => p?.[0]?.payload?.date ?? ""}
          />
          <Bar dataKey="count" name="Incidents" fill="#38bdf8" radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function NamedBarChart({ data, color = "#34d399" }: { data: NamedCount[]; color?: string }) {
  if (!data.length) {
    return (
      <p className="flex h-40 items-center justify-center text-sm text-zinc-500">
        No data
      </p>
    );
  }
  return (
    <div className="h-40 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 4, right: 8, left: 8, bottom: 0 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#3f3f46" horizontal={false} />
          <XAxis type="number" allowDecimals={false} tick={{ fill: "#a1a1aa", fontSize: 11 }} />
          <YAxis
            type="category"
            dataKey="name"
            width={88}
            tick={{ fill: "#a1a1aa", fontSize: 10 }}
          />
          <Tooltip
            contentStyle={{
              background: "#18181b",
              border: "1px solid #3f3f46",
              borderRadius: 8,
              fontSize: 12,
            }}
          />
          <Bar dataKey="count" fill={color} radius={[0, 3, 3, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function NamedPieChart({ data }: { data: NamedCount[] }) {
  if (!data.length) {
    return (
      <p className="flex h-40 items-center justify-center text-sm text-zinc-500">
        No data
      </p>
    );
  }
  return (
    <div className="h-40 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            dataKey="count"
            nameKey="name"
            cx="50%"
            cy="50%"
            innerRadius={36}
            outerRadius={60}
            paddingAngle={2}
          >
            {data.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{
              background: "#18181b",
              border: "1px solid #3f3f46",
              borderRadius: 8,
              fontSize: 12,
            }}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}