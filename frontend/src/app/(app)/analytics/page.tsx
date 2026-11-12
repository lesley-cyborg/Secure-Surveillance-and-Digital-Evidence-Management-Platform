"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Download, RefreshCw } from "lucide-react";
import {
  loadAnalytics,
  type AnalyticsBundle,
} from "@/features/analytics/api";
import type { RangeDays } from "@/features/analytics/aggregate";
import {
  NamedBarChart,
  NamedPieChart,
  TrendBarChart,
} from "@/features/analytics/charts";
import { buildAnalyticsCsv, downloadCsv } from "@/features/analytics/csv";
import { downloadServerExport } from "@/features/analytics/exportApi";
import { canExportReports } from "@/lib/permissions";

export default function AnalyticsPage() {
  const [rangeDays, setRangeDays] = useState<RangeDays>(7);
  const [cameraId, setCameraId] = useState<string>("");
  const [data, setData] = useState<AnalyticsBundle | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  
  // 👇 1. Add mounted state to track client-side rendering
  const [mounted, setMounted] = useState(false);

  // 👇 2. Set mounted to true only after the component mounts on the client
  useEffect(() => {
    setMounted(true);
  }, []);

  const canExport = canExportReports();

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await loadAnalytics(rangeDays, cameraId || null));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load analytics");
    } finally {
      setLoading(false);
    }
  }, [rangeDays, cameraId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const onlineRatio = useMemo(() => {
    if (!data?.cameras.length) return "—";
    const online = data.cameras.filter((c) =>
      ["ONLINE", "ACTIVE"].includes((c.status || "").toUpperCase()),
    ).length;
    const pct = Math.round((online / data.cameras.length) * 100);
    return `${online}/${data.cameras.length} (${pct}%)`;
  }, [data]);

  function onExportClient() {
    if (!data || !canExport) return;
    setExportError(null);
    const stamp = new Date()
      .toISOString()
      .slice(0, 19)
      .replace(/[:T]/g, "-");
    downloadCsv(
      `analytics-${data.rangeDays}d-${stamp}.csv`,
      buildAnalyticsCsv(data),
    );
  }

  async function onExportServer() {
    if (!canExport) return;
    setExportError(null);
    setExporting(true);
    try {
      await downloadServerExport("incidents", {
        days: rangeDays,
        cameraId: cameraId || undefined,
      });
    } catch (e) {
      setExportError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">
            Insights
          </p>
          <h1 className="mt-1 text-2xl font-semibold text-zinc-50">Analytics</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Trends and breakdowns from operational data (API sample limits apply)
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {canExport && (
            <>
              <button
                type="button"
                onClick={onExportClient}
                disabled={!data || loading}
                className="inline-flex items-center gap-2 rounded-md border border-zinc-700 px-3 py-2 text-xs text-zinc-300 hover:border-zinc-500 disabled:opacity-50"
              >
                <Download className="h-3.5 w-3.5" />
                Export (client)
              </button>
              <button
                type="button"
                onClick={() => void onExportServer()}
                disabled={loading || exporting}
                className="inline-flex items-center gap-2 rounded-md border border-zinc-700 px-3 py-2 text-xs text-zinc-300 hover:border-zinc-500 disabled:opacity-50"
              >
                <Download className="h-3.5 w-3.5" />
                {exporting ? "Exporting…" : "Export (server)"}
              </button>
            </>
          )}
          <button
            type="button"
            onClick={() => void refresh()}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-md border border-zinc-700 px-3 py-2 text-xs text-zinc-300 hover:border-zinc-500 disabled:opacity-50"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`}
            />
            Refresh
          </button>
        </div>
      </div>

      {!canExport && (
        <p className="text-[11px] text-zinc-600">
          CSV export requires reports.export (or equivalent) permission.
        </p>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-zinc-800 bg-zinc-900/40 p-3">
        <div>
          <label className="mb-1 block text-[11px] uppercase tracking-wide text-zinc-500">
            Range
          </label>
          <div className="flex gap-1">
            {([7, 14, 30] as RangeDays[]).map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => setRangeDays(d)}
                className={`rounded-md px-3 py-1.5 text-xs ${
                  rangeDays === d
                    ? "bg-zinc-100 text-zinc-900"
                    : "border border-zinc-700 text-zinc-400 hover:border-zinc-500"
                }`}
              >
                {d}d
              </button>
            ))}
          </div>
        </div>
        <div className="min-w-[12rem] flex-1">
          <label className="mb-1 block text-[11px] uppercase tracking-wide text-zinc-500">
            Camera (optional)
          </label>
          <select
            value={cameraId}
            onChange={(e) => setCameraId(e.target.value)}
            className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-100"
          >
            <option value="">All cameras</option>
            {(data?.cameras ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.cameraCode})
              </option>
            ))}
          </select>
        </div>
      </div>

      {error && (
        <p className="rounded-md border border-red-900/50 bg-red-950/40 px-3 py-2 text-sm text-red-300">
          {error}
        </p>
      )}
      {exportError && (
        <p className="rounded-md border border-red-900/50 bg-red-950/40 px-3 py-2 text-sm text-red-300">
          {exportError}
        </p>
      )}

      {/* Summary chips */}
      <div className="flex flex-wrap gap-2">
        {[
          {
            label: "Incidents in range",
            value: data ? String(data.incidentsFiltered.length) : "—",
          },
          {
            label: "Open (in range)",
            value: data ? String(data.openCount) : "—",
          },
          { label: "Cameras online", value: onlineRatio },
          {
            label: "Evidence loaded",
            value: data ? String(data.evidence.length) : "—",
          },
          {
            label: "Custody events (sample)",
            value: data ? String(data.custodyEventsSampled) : "—",
          },
        ].map((chip) => (
          <div
            key={chip.label}
            className="rounded-full border border-zinc-800 bg-zinc-900/80 px-3 py-1 text-xs text-zinc-400"
          >
            <span className="text-zinc-500">{chip.label}: </span>
            <span className="font-medium text-zinc-200">{chip.value}</span>
          </div>
        ))}
      </div>

      {/* Trend */}
      <section className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
        <h2 className="text-sm font-medium text-zinc-100">
          Incident volume ({rangeDays} days)
        </h2>
        <p className="text-xs text-zinc-600">
          Bucketed by detectedAt / createdAt
        </p>
        <div className="mt-2">
          {data ? <TrendBarChart data={data.trend} /> : <LoadingBlock />}
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <h2 className="text-sm font-medium text-zinc-100">By status</h2>
          {data ? (
            <NamedBarChart data={data.byStatus} color="#38bdf8" />
          ) : (
            <LoadingBlock />
          )}
        </section>
        <section className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <h2 className="text-sm font-medium text-zinc-100">By severity</h2>
          {data ? (
            <NamedBarChart data={data.bySeverity} color="#fbbf24" />
          ) : (
            <LoadingBlock />
          )}
        </section>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <h2 className="text-sm font-medium text-zinc-100">By source</h2>
          <p className="text-xs text-zinc-600">AI vs MANUAL (and others)</p>
          {data ? <NamedPieChart data={data.bySource} /> : <LoadingBlock />}
          {data && data.bySource.length > 0 && (
            <ul className="mt-2 flex flex-wrap gap-2 text-[11px] text-zinc-500">
              {data.bySource.map((s) => (
                <li key={s.name}>
                  {s.name}: {s.count}
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <h2 className="text-sm font-medium text-zinc-100">Camera health</h2>
          <p className="text-xs text-zinc-600">Share of fleet by status</p>
          {data ? (
            <NamedBarChart data={data.cameraHealth} color="#34d399" />
          ) : (
            <LoadingBlock />
          )}
        </section>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <h2 className="text-sm font-medium text-zinc-100">Evidence by status</h2>
          {data ? (
            <NamedBarChart data={data.evidenceStatus} color="#a78bfa" />
          ) : (
            <LoadingBlock />
          )}
        </section>
        <section className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <h2 className="text-sm font-medium text-zinc-100">Evidence by type</h2>
          {data ? (
            <NamedPieChart data={data.evidenceType} />
          ) : (
            <LoadingBlock />
          )}
        </section>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <h2 className="text-sm font-medium text-zinc-100">Top incident types</h2>
          {!data ? (
            <LoadingBlock />
          ) : data.topTypes.length === 0 ? (
            <p className="mt-3 text-sm text-zinc-500">No types in range</p>
          ) : (
            <table className="mt-3 w-full text-left text-sm">
              <thead className="text-xs uppercase text-zinc-500">
                <tr>
                  <th className="pb-2 font-medium">Type</th>
                  <th className="pb-2 font-medium">Count</th>
                </tr>
              </thead>
              <tbody>
                {data.topTypes.map((t) => (
                  <tr key={t.name} className="border-t border-zinc-800">
                    <td className="py-2 text-zinc-200">{t.name}</td>
                    <td className="py-2 text-zinc-400">{t.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <h2 className="text-sm font-medium text-zinc-100">
            High severity (recent in range)
          </h2>
          {!data ? (
            <LoadingBlock />
          ) : data.highSeverity.length === 0 ? (
            <p className="mt-3 text-sm text-zinc-500">None in range</p>
          ) : (
            <ul className="mt-3 divide-y divide-zinc-800">
              {data.highSeverity.map((inc) => (
                <li key={inc.id}>
                  <Link
                    href={`/incidents/${inc.id}`}
                    className="flex justify-between gap-2 py-2 text-sm hover:bg-zinc-900/50"
                  >
                    <span className="min-w-0 truncate text-zinc-200">
                      {inc.title || inc.incidentNumber}
                    </span>
                    <span className="shrink-0 text-xs text-zinc-500">
                      {inc.severity} · {inc.status}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <p className="text-[11px] text-zinc-600">
        Analytics uses list API samples (incidents ≤200, evidence ≤100). Custody
        counts are sampled from up to 5 evidence timelines. Server export uses
        GET /api/v1/reports/export/* when available.
      </p>
    </div>
  );
}

function LoadingBlock() {
  return (
    <p className="flex h-32 items-center justify-center text-sm text-zinc-500">
      Loading…
    </p>
  );
}