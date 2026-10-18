"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Shield, Clock, Eye } from "lucide-react";
import { listIncidents } from "@/features/incidents/api";
import type { Incident, Severity, IncidentStatus } from "@/types/incident";

const getSeverityColor = (severity: Severity) => {
  switch (severity) {
    case "CRITICAL": return "bg-red-500/10 text-red-400 border-red-500/20";
    case "HIGH": return "bg-orange-500/10 text-orange-400 border-orange-500/20";
    case "MEDIUM": return "bg-yellow-500/10 text-yellow-400 border-yellow-500/20";
    case "LOW": return "bg-blue-500/10 text-blue-400 border-blue-500/20";
    default: return "bg-zinc-500/10 text-zinc-400 border-zinc-500/20";
  }
};

const getStatusColor = (status: IncidentStatus) => {
  switch (status) {
    case "NEW": return "text-emerald-400";
    case "INVESTIGATING": return "text-amber-400";
    case "RESOLVED": case "CLOSED": return "text-zinc-500";
    default: return "text-zinc-300";
  }
};

export default function IncidentsPage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listIncidents(50, 0);
      setIncidents(data.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load incidents");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">
            Security Operations
          </p>
          <h1 className="mt-1 text-2xl font-semibold text-zinc-50">Incidents</h1>
          <p className="mt-1 text-sm text-zinc-500">
            AI-detected anomalies and security events
          </p>
        </div>
        <button
          type="button"
          onClick={() => void refresh()}
          disabled={loading}
          className="rounded-md border border-zinc-700 px-3 py-2 text-xs text-zinc-300 hover:border-zinc-500 disabled:opacity-50 transition"
        >
          Refresh
        </button>
      </div>

      {loading ? (
        <p className="text-sm text-zinc-500">Loading incidents…</p>
      ) : error ? (
        <p className="text-sm text-red-400">{error}</p>
      ) : incidents.length === 0 ? (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-8 text-center">
          <Shield className="mx-auto h-8 w-8 text-zinc-600" />
          <p className="mt-3 text-sm text-zinc-400">No incidents detected yet.</p>
          <p className="mt-1 text-xs text-zinc-600">
            Ensure your AI engine is running and detecting events.
          </p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900/60">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-zinc-800 bg-zinc-950/50 text-xs uppercase tracking-wide text-zinc-500">
                <tr>
                  <th className="px-4 py-3 font-medium">Severity</th>
                  <th className="px-4 py-3 font-medium">Incident</th>
                  <th className="px-4 py-3 font-medium">Camera</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Detected</th>
                  <th className="px-4 py-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800">
                {incidents.map((incident) => (
                  <tr key={incident.id} className="transition hover:bg-zinc-800/30">
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium ${getSeverityColor(incident.severity)}`}>
                        <AlertTriangle className="h-3 w-3" />
                        {incident.severity}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <p className="font-medium text-zinc-100">{incident.title}</p>
                      <p className="text-xs text-zinc-500">{incident.incidentNumber}</p>
                    </td>
                    <td className="px-4 py-3 text-zinc-400">
                      {incident.primaryCameraId ? (
                        <span className="font-mono text-xs">{incident.primaryCameraId.slice(0, 8)}...</span>
                      ) : (
                        <span className="text-zinc-600">Unknown</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-xs font-medium ${getStatusColor(incident.status)}`}>
                        {incident.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-zinc-400">
                      <div className="flex items-center gap-1.5">
                        <Clock className="h-3.5 w-3.5" />
                        {new Date(incident.detectedAt).toLocaleString()}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300 transition">
                        <Eye className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}