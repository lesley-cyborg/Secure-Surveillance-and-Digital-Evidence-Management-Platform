"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Scale,
  Search,
  ArrowRight,
  Shield,
  GitBranch,
} from "lucide-react";

export default function CustodyPage() {
  const router = useRouter();
  const [evidenceId, setEvidenceId] = useState("");
  const [error, setError] = useState<string | null>(null);

  function onLookup(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const id = evidenceId.trim();
    if (!id) {
      setError("Enter an evidence UUID");
      return;
    }
    // Basic UUID shape check (optional)
    const uuidRe =
      /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
    if (!uuidRe.test(id)) {
      setError("Evidence id must be a valid UUID");
      return;
    }
    router.push(`/evidence/${id}`);
  }

  return (
    <div className="space-y-6 p-6">
      <span className="hidden text-emerald-400 text-amber-400 text-sky-400" />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">
            Forensics
          </p>
          <h1 className="mt-1 text-2xl font-semibold text-zinc-50">
            Chain of custody
          </h1>
          <p className="mt-1 text-sm text-zinc-500">
            Transfers, accept/reject decisions, and signed custody events
          </p>
        </div>
        <Link
          href="/evidence"
          className="inline-flex items-center gap-2 rounded-md border border-zinc-700 px-3 py-2 text-xs text-zinc-300 hover:border-zinc-500"
        >
          Evidence directory
          <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>

      {/* KPI-style cards */}
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <div className="flex items-center gap-2 text-zinc-500">
            <Scale className="h-4 w-4" />
            <p className="text-xs uppercase tracking-wide">Workflow</p>
          </div>
          <p className="mt-2 text-sm text-zinc-300">
            Initiate → Pending → Accept / Reject
          </p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <div className="flex items-center gap-2 text-zinc-500">
            <GitBranch className="h-4 w-4" />
            <p className="text-xs uppercase tracking-wide">Timeline</p>
          </div>
          <p className="mt-2 text-sm text-zinc-300">
            Per-evidence custody events (hashed records)
          </p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <div className="flex items-center gap-2 text-zinc-500">
            <Shield className="h-4 w-4" />
            <p className="text-xs uppercase tracking-wide">Access</p>
          </div>
          <p className="mt-2 text-sm text-zinc-300">
            Recipient-only decisions · RBAC enforced
          </p>
        </div>
      </div>

      {/* Jump to evidence custody panel */}
      <section className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4 space-y-4">
        <div>
          <h2 className="text-sm font-medium text-zinc-100">
            Open custody for evidence
          </h2>
          <p className="mt-1 text-xs text-zinc-500">
            There is no global transfer inbox in the API. Open an evidence item
            to view history, initiate a transfer, or accept/reject as recipient.
          </p>
        </div>

        <form onSubmit={onLookup} className="flex flex-col gap-3 sm:flex-row">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-600" />
            <input
              value={evidenceId}
              onChange={(e) => setEvidenceId(e.target.value)}
              placeholder="Evidence UUID Format: 8-4-4-4-12 hex digits"
              className="w-full rounded-md border border-zinc-700 bg-zinc-950 py-2 pl-9 pr-3 font-mono text-sm text-zinc-100 outline-none focus:border-zinc-500"
            />
          </div>
          <button
            type="submit"
            className="rounded-md border border-zinc-700 bg-zinc-800 px-4 py-2 text-xs font-medium text-zinc-200 hover:bg-zinc-700"
          >
            Open evidence
          </button>
        </form>

        {error && (
          <p className="text-sm text-red-400">{error}</p>
        )}
      </section>

      {/* How it works */}
      <section className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
        <h2 className="text-xs font-medium uppercase tracking-wide text-zinc-500">
          Operator steps
        </h2>
        <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm text-zinc-400">
          <li>
            Open{" "}
            <Link href="/evidence" className="text-zinc-200 underline-offset-2 hover:underline">
              Evidence
            </Link>{" "}
            and select a record (or paste UUID above).
          </li>
          <li>
            On the detail page, use <span className="text-zinc-300">Chain of custody</span> to
            initiate a transfer (purpose + recipient).
          </li>
          <li>
            Recipient signs in, opens the same evidence, and Accepts or Rejects.
          </li>
          <li>
            History refreshes from{" "}
            <code className="text-[11px] text-zinc-500">
              GET /api/v1/evidence/&#123;id&#125;/custody-events
            </code>
            .
          </li>
        </ol>
      </section>
    </div>
  );
}