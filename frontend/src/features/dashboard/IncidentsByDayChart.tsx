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

type Point = { date: string; label: string; count: number };

export function IncidentsByDayChart({ data }: { data: Point[] }) {
  const empty = data.every((d) => d.count === 0);

  return (
    <div className="h-56 w-full">
      {empty ? (
        <p className="flex h-full items-center justify-center text-sm text-zinc-500">
          No incidents in the last 7 days (from loaded sample)
        </p>
      ) : (
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#3f3f46" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fill: "#a1a1aa", fontSize: 11 }}
              axisLine={{ stroke: "#3f3f46" }}
              tickLine={false}
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
              labelStyle={{ color: "#e4e4e7" }}
              itemStyle={{ color: "#a1a1aa" }}
              labelFormatter={(_, payload) =>
                payload?.[0]?.payload?.date ?? ""
              }
            />
            <Bar dataKey="count" name="Incidents" fill="#38bdf8" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}