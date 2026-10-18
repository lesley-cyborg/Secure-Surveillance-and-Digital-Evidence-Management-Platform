import { apiRequest } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";
import type {
  Evidence,
  EvidenceListResponse,
  EvidenceVerification,
} from "@/types/evidence";

function idempotencyKey(): string {
  const a = crypto.randomUUID().replace(/-/g, "");
  const b = crypto.randomUUID().replace(/-/g, "");
  return (a + b).slice(0, 32); // ≥16 chars
}

export type ListEvidenceParams = {
  incidentId?: string;
  status?: string;
  limit?: number;
  offset?: number;
};

export async function listEvidence(
  params: ListEvidenceParams = {},
): Promise<EvidenceListResponse> {
  const q = new URLSearchParams();
  if (params.incidentId) q.set("incidentId", params.incidentId);
  if (params.status) q.set("status", params.status);
  if (params.limit != null) q.set("limit", String(params.limit));
  if (params.offset != null) q.set("offset", String(params.offset));
  const qs = q.toString();
  return apiRequest<EvidenceListResponse>(
    `/api/v1/evidence${qs ? `?${qs}` : ""}`,
  );
}

export async function getEvidence(id: string): Promise<Evidence> {
  return apiRequest<Evidence>(`/api/v1/evidence/${id}`);
}

export async function verifyEvidence(
  id: string,
): Promise<EvidenceVerification> {
  return apiRequest<EvidenceVerification>(`/api/v1/evidence/${id}/verify`, {
    method: "POST",
    headers: {
      "Idempotency-Key": idempotencyKey(),
    },
  });
}

/**
 * Authenticated blob download/preview.
 * Requires evidence.content.read on the server.
 */
export async function fetchEvidenceContent(
  id: string,
  disposition: "inline" | "attachment" = "attachment",
): Promise<{ blob: Blob; filename: string | null }> {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
  const token = getAccessToken();
  if (!token) {
    throw new Error("Not authenticated");
  }

  const res = await fetch(
    `${base}/api/v1/evidence/${id}/content?disposition=${disposition}`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    },
  );

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Download failed (${res.status})`);
  }

  const cd = res.headers.get("Content-Disposition");
  let filename: string | null = null;
  const star = cd?.match(/filename\*=UTF-8''([^;]+)/i);
  if (star?.[1]) {
    filename = decodeURIComponent(star[1]);
  }

  return { blob: await res.blob(), filename };
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}