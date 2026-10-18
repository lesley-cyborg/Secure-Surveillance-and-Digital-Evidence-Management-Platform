import type { EvidenceStatus, VerificationStatus } from "@/types/evidence";

export function evidenceStatusClass(status: EvidenceStatus): string {
  switch (status) {
    case "VERIFIED":
      return "text-emerald-400";
    case "STORED":
      return "text-sky-400";
    case "PENDING":
      return "text-amber-400";
    case "COMPROMISED":
    case "QUARANTINED":
      return "text-red-400";
    default:
      return "text-zinc-400";
  }
}

export function verificationClass(status: VerificationStatus): string {
  if (status === "VERIFIED") return "text-emerald-400";
  if (status === "HASH_MISMATCH" || status === "SIGNATURE_INVALID") {
    return "text-red-400";
  }
  return "text-amber-400";
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function shortHash(hash: string, n = 12): string {
  if (hash.length <= n * 2) return hash;
  return `${hash.slice(0, n)}…${hash.slice(-n)}`;
}