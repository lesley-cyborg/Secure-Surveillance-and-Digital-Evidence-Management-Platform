"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, Download, ShieldCheck, Loader2 } from "lucide-react";
import {
  downloadBlob,
  fetchEvidenceContent,
  getEvidence,
  verifyEvidence,
} from "@/features/evidence/api";
import {
  evidenceStatusClass,
  formatBytes,
  verificationClass,
} from "@/features/evidence/statusStyles";
import {
  canDownloadEvidence,
  canVerifyEvidence,
} from "@/lib/permissions";
import type { Evidence, EvidenceVerification } from "@/types/evidence";
import { CustodyPanel } from "@/features/custody/CustodyPanel";

export default function EvidenceDetailPage() {
  const params = useParams();
  const id = String(params.id ?? "");

  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [verification, setVerification] = useState<EvidenceVerification | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [actionMsg, setActionMsg] = useState<string | null>(null);

  const showDownload = canDownloadEvidence();
  const showVerify = canVerifyEvidence();

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      setEvidence(await getEvidence(id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load evidence");
      setEvidence(null);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  async function onVerify() {
    setVerifying(true);
    setActionMsg(null);
    try {
      const result = await verifyEvidence(id);
      setVerification(result);
      setActionMsg(
        result.hashMatches && result.signatureValid
          ? "Integrity and signature verified"
          : result.failureReason || "Verification completed with issues",
      );
      await load();
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : "Verification failed");
    } finally {
      setVerifying(false);
    }
  }

  async function onDownload() {
    if (!showDownload || !evidence) return;
    setDownloading(true);
    setActionMsg(null);
    try {
      const { blob, filename } = await fetchEvidenceContent(
        id,
        "attachment",
      );
      downloadBlob(
        blob,
        filename || evidence.originalFilename || "evidence.bin",
      );
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : "Download failed");
    } finally {
      setDownloading(false);
    }
  }

  if (loading) {
    return (
      <div className="p-6 text-sm text-zinc-500">Loading evidence…</div>
    );
  }

  if (error || !evidence) {
    return (
      <div className="space-y-4 p-6">
        <Link
          href="/evidence"
          className="inline-flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-200"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> Back to evidence
        </Link>
        <p className="text-sm text-red-400">{error ?? "Not found"}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      <span className="hidden text-emerald-400 text-sky-400 text-amber-400 text-red-400" />

      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <Link
            href="/evidence"
            className="inline-flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> Evidence
          </Link>
          <h1 className="mt-2 text-xl font-semibold text-zinc-50">
            {evidence.evidenceNumber}
          </h1>
          <p className="mt-1 text-sm text-zinc-500">{evidence.originalFilename}</p>
          <p className={`mt-2 text-xs font-medium ${evidenceStatusClass(evidence.status)}`}>
            {evidence.status}
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          {showVerify && (
            <button
              type="button"
              onClick={() => void onVerify()}
              disabled={verifying}
              className="inline-flex items-center gap-2 rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-xs font-medium text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
            >
              {verifying ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <ShieldCheck className="h-3.5 w-3.5" />
              )}
              Verify integrity
            </button>
          )}

          {/* Download only if JWT user has evidence.content.read */}
          {showDownload && (
            <button
              type="button"
              onClick={() => void onDownload()}
              disabled={downloading}
              className="inline-flex items-center gap-2 rounded-md border border-zinc-700 px-3 py-2 text-xs font-medium text-zinc-300 hover:bg-zinc-900 disabled:opacity-50"
            >
              {downloading ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Download className="h-3.5 w-3.5" />
              )}
              Download
            </button>
          )}
        </div>
      </div>

      {actionMsg && (
        <p className="rounded-md border border-zinc-800 bg-zinc-900/80 px-3 py-2 text-sm text-zinc-300">
          {actionMsg}
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4 space-y-3">
          <h2 className="text-xs font-medium uppercase tracking-wide text-zinc-500">
            Metadata
          </h2>
          <dl className="space-y-2 text-sm">
            <Row label="ID" value={evidence.id} mono />
            <Row label="Incident" value={evidence.incidentId} mono />
            <Row label="Type" value={`${evidence.evidenceType} / ${evidence.sourceType}`} />
            <Row label="MIME" value={evidence.mimeType} />
            <Row label="Size" value={formatBytes(evidence.fileSizeBytes)} />
            <Row
              label="Captured"
              value={new Date(evidence.capturedAt).toLocaleString()}
            />
            <Row
              label="Ingested"
              value={new Date(evidence.ingestedAt).toLocaleString()}
            />
          </dl>
        </section>

        <section className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4 space-y-3">
          <h2 className="text-xs font-medium uppercase tracking-wide text-zinc-500">
            Integrity
          </h2>
          <dl className="space-y-2 text-sm">
            <Row label="Original SHA-256" value={evidence.originalSha256} mono />
            <Row label="Encrypted SHA-256" value={evidence.encryptedSha256} mono />
          </dl>

          {verification && (
            <div className="mt-4 space-y-2 border-t border-zinc-800 pt-3 text-sm">
              <p className={`font-medium ${verificationClass(verification.verificationStatus)}`}>
                {verification.verificationStatus}
              </p>
              <p className="text-xs text-zinc-500">
                Hash matches: {verification.hashMatches ? "yes" : "no"} · Signature:{" "}
                {verification.signatureValid ? "valid" : "invalid"}
              </p>
              {verification.calculatedSha256 && (
                <p className="break-all font-mono text-[11px] text-zinc-500">
                  Calculated: {verification.calculatedSha256}
                </p>
              )}
              <p className="text-xs text-zinc-600">
                Verified at {new Date(verification.verifiedAt).toLocaleString()}
              </p>
            </div>
          )}
        </section>
      </div>
      <CustodyPanel evidenceId={evidence.id} />
    </div>
  );
}

function Row({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex flex-col gap-0.5 sm:flex-row sm:gap-3">
      <dt className="w-36 shrink-0 text-xs text-zinc-500">{label}</dt>
      <dd
        className={`min-w-0 break-all text-zinc-200 ${mono ? "font-mono text-xs" : ""}`}
      >
        {value}
      </dd>
    </div>
  );
}