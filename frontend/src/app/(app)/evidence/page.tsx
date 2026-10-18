"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Shield, RefreshCw } from "lucide-react";
import { listEvidence } from "@/features/evidence/api";
import {
  evidenceStatusClass,
  formatBytes,
  shortHash,
} from "@/features/evidence/statusStyles";
import type { Evidence } from "@/types/evidence";

export default function EvidencePage() {
  const [items, setItems] = useState<Evidence[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listEvidence({ limit: 50 });
      setItems(data.items ?? []);
      setTotal(data.total ?? 0);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load evidence");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <div className="space-y-6 p-6">
      <span className="hidden text-emerald-400 text-sky-400 text-amber-400 text-red-400" />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">
            Forensics
          </p>
          <h1 className="mt-1 text-2xl font-semibold text-zinc-50">Evidence</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Secured artifacts — integrity, encryption, chain of custody
          </p>
        </div>
        <button
          type="button"
          onClick={() => void refresh()}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-md border border-zinc-700 px-3 py-2 text-xs text-zinc-300 hover:border-zinc-500 disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <p className="text-xs uppercase tracking-wide text-zinc-500">Total</p>
          <p className="mt-2 text-2xl font-semibold text-zinc-50">{total}</p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <p className="text-xs uppercase tracking-wide text-zinc-500">Loaded</p>
          <p className="mt-2 text-2xl font-semibold text-zinc-50">{items.length}</p>
        </div>
      </div>

      {error && (
        <p className="rounded-md border border-red-900/50 bg-red-950/40 px-3 py-2 text-sm text-red-300">
          {error}
        </p>
      )}

      {loading ? (
        <p className="text-sm text-zinc-500">Loading evidence…</p>
      ) : items.length === 0 ? (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-8 text-center">
          <Shield className="mx-auto h-8 w-8 text-zinc-600" />
          <p className="mt-3 text-sm text-zinc-400">No evidence records yet.</p>
          <p className="mt-1 text-xs text-zinc-600">
            Artifacts appear after secure ingestion (AI or manual).
          </p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-zinc-800">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-zinc-800 bg-zinc-900/80 text-xs uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="px-4 py-3 font-medium">Evidence</th>
                <th className="px-4 py-3 font-medium">Type</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">SHA-256</th>
                <th className="px-4 py-3 font-medium">Size</th>
                <th className="px-4 py-3 font-medium">Ingested</th>
              </tr>
            </thead>
            <tbody>
              {items.map((e) => (
                <tr
                  key={e.id}
                  className="border-b border-zinc-800/80 hover:bg-zinc-900/40"
                >
                  <td className="px-4 py-3">
                    <Link
                      href={`/evidence/${e.id}`}
                      className="font-medium text-zinc-100 hover:text-white"
                    >
                      {e.evidenceNumber}
                    </Link>
                    <p className="truncate text-xs text-zinc-500 max-w-[14rem]">
                      {e.originalFilename}
                    </p>
                  </td>
                  <td className="px-4 py-3 text-xs text-zinc-400">
                    {e.evidenceType}
                    <span className="block text-zinc-600">{e.sourceType}</span>
                  </td>
                  <td className={`px-4 py-3 text-xs font-medium ${evidenceStatusClass(e.status)}`}>
                    {e.status}
                  </td>
                  <td className="px-4 py-3 font-mono text-[11px] text-zinc-500">
                    {shortHash(e.originalSha256)}
                  </td>
                  <td className="px-4 py-3 text-xs text-zinc-400">
                    {formatBytes(e.fileSizeBytes)}
                  </td>
                  <td className="px-4 py-3 text-xs text-zinc-500">
                    {new Date(e.ingestedAt).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
