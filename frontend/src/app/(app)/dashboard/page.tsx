"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  Camera,
  AlertTriangle,
  Shield,
  RefreshCw,
  Scale,
} from "lucide-react";
import {
  loadDashboardStats,
  type DashboardStats,
} from "@/features/dashboard/api";
import { IncidentsByDayChart } from "@/features/dashboard/IncidentsByDayChart";

const REFRESH_MS = 30_000;

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const refresh = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      const data = await loadDashboardStats();
      setStats(data);
      setLastUpdated(new Date());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load dashboard");
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh(false);
  }, [refresh]);

  // Auto-refresh every 30s (silent — no full-page spinner)
  useEffect(() => {
    const id = window.setInterval(() => {
      void refresh(true);
    }, REFRESH_MS);
    return () => window.clearInterval(id);
  }, [refresh]);

  const cards = [
    {
      label: "Cameras",
      value: stats ? `${stats.camerasOnline} / ${stats.camerasTotal}` : "—",
      hint: "Online / registered",
      href: "/cameras",
      icon: Camera,
    },
    {
      label: "Open incidents",
      value: stats ? String(stats.incidentsOpen) : "—",
      hint: stats ? `${stats.incidentsTotal} total` : "Incidents",
      href: "/incidents",
      icon: AlertTriangle,
    },
    {
      label: "Evidence",
      value: stats ? String(stats.evidenceTotal) : "—",
      hint: "Secured artifacts",
      href: "/evidence",
      icon: Shield,
    },
    {
      label: "Custody events",
      value: stats ? String(stats.custodyEventsSampled) : "—",
      hint: stats
        ? `Sampled from ${stats.custodyEvidenceSampled} evidence item(s)`
        : "Chain of custody",
      href: "/custody",
      icon: Scale,
    },
  ];

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">
            Operations
          </p>
          <h1 className="mt-1 text-2xl font-semibold text-zinc-50">Dashboard</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Live overview — Monitor · Detect · Investigate · Preserve
          </p>
          {lastUpdated && (
            <p className="mt-1 text-[11px] text-zinc-600">
              Updated {lastUpdated.toLocaleTimeString()} · auto every 30s
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={() => void refresh(false)}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-md border border-zinc-700 px-3 py-2 text-xs text-zinc-300 transition hover:border-zinc-500 disabled:opacity-50"
        >
          <RefreshCw
            className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`}
          />
          Refresh
        </button>
      </div>

      {error && (
        <p className="rounded-md border border-red-900/50 bg-red-950/40 px-3 py-2 text-sm text-red-300">
          {error}
        </p>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map((c) => (
          <Link
            key={c.label}
            href={c.href}
            className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4 transition hover:border-zinc-700"
          >
            <div className="flex items-center justify-between">
              <p className="text-xs uppercase tracking-wide text-zinc-500">
                {c.label}
              </p>
              <c.icon className="h-4 w-4 text-zinc-600" />
            </div>
            <p className="mt-2 text-2xl font-semibold text-zinc-50">
              {loading && !stats ? "…" : c.value}
            </p>
            <p className="mt-1 text-xs text-zinc-600">{c.hint}</p>
          </Link>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <h2 className="text-sm font-medium text-zinc-100">
            Incidents by day (7 days)
          </h2>
          <p className="mt-0.5 text-xs text-zinc-600">
            From loaded incident sample (detectedAt / createdAt)
          </p>
          <div className="mt-3">
            {stats ? (
              <IncidentsByDayChart data={stats.incidentsByDay} />
            ) : (
              <p className="py-16 text-center text-sm text-zinc-500">Loading…</p>
            )}
          </div>
        </section>

        <section className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-sm font-medium text-zinc-100">Recent incidents</h2>
            <Link
              href="/incidents"
              className="text-xs text-zinc-500 hover:text-zinc-300"
            >
              View all
            </Link>
          </div>

          {loading && !stats ? (
            <p className="mt-4 text-sm text-zinc-500">Loading…</p>
          ) : !stats?.recentIncidents.length ? (
            <p className="mt-4 text-sm text-zinc-500">No incidents to show.</p>
          ) : (
            <ul className="mt-3 divide-y divide-zinc-800">
              {stats.recentIncidents.map((inc) => (
                <li key={inc.id}>
                  <Link
                    href={`/incidents/${inc.id}`}
                    className="flex items-center justify-between gap-3 py-2.5 text-sm transition hover:bg-zinc-900/50"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-zinc-200">
                        {inc.title?.trim() || inc.incidentNumber}
                      </p>
                      <p className="truncate text-[11px] text-zinc-600">
                        {inc.incidentNumber}
                        {inc.severity ? ` · ${inc.severity}` : ""}
                        {inc.sourceType ? ` · ${inc.sourceType}` : ""}
                      </p>
                    </div>
                    <span className="shrink-0 text-xs text-zinc-500">
                      {inc.status}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <p className="text-[11px] text-zinc-600">
        Phase 2: 7-day bar chart, custody sample from evidence timelines, 30s
        auto-refresh. Counts are limited by list API page size until aggregate
        endpoints exist.
      </p>
    </div>
  );
}