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

// 👇 Define API base URL
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

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

  const handleDownload = async (evidenceId: string, filename: string) => {
    try {
      const token = getAccessToken();
      if (!token) throw new Error("Not authenticated");

      // Use the existing /content endpoint with disposition=attachment
      const res = await fetch(`${API_BASE}/api/v1/evidence/${evidenceId}/content?disposition=attachment`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!res.ok) throw new Error("Failed to download");

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename || "evidence_file";
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      a.remove();
    } catch (err) {
      console.error("Download error:", err);
      alert("Failed to download evidence.");
    }
  };

  const handleVerify = async (evidenceId: string) => {
    try {
      const token = getAccessToken();
      if (!token) throw new Error("Not authenticated");

      // Your backend requires an Idempotency-Key for the verify endpoint
      const idempotencyKey = crypto.randomUUID();

      const res = await fetch(`${API_BASE}/api/v1/evidence/${evidenceId}/verify`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Idempotency-Key": idempotencyKey, // 👈 Crucial for your backend
          "Content-Type": "application/json",
        },
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail?.message || `HTTP ${res.status}`);
      }

      const data = await res.json();

      if (data.verificationStatus === "VERIFIED") {
        alert(`✅ VERIFIED\n\nEvidence integrity and authenticity confirmed.`);
      } else {
        alert(`⚠️ VERIFICATION FAILED\n\nStatus: ${data.verificationStatus}`);
      }

      // Refresh the evidence list to show updated verification status
      void refresh();
    } catch (err) {
      console.error("Verification error:", err);
      alert(`Failed to verify evidence: ${err instanceof Error ? err.message : "Unknown error"}`);
    }
  };

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
                <th className="px-4 py-3 font-medium text-right">Actions</th>
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
                  {/* 👇 Added Actions Column */}
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => handleVerify(e.id)}
                        className="inline-flex items-center gap-1.5 rounded-md bg-emerald-600 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-emerald-500 transition-colors"
                        title="Verify cryptographic integrity"
                      >
                        <ShieldCheck className="h-3.5 w-3.5" />
                        Verify
                      </button>
                      <button
                        onClick={() => handleDownload(e.id, e.originalFilename)}
                        className="inline-flex items-center gap-1.5 rounded-md bg-zinc-700 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-zinc-600 transition-colors"
                        title="Download evidence file"
                      >
                        <Download className="h-3.5 w-3.5" />
                        Download
                      </button>
                    </div>
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
