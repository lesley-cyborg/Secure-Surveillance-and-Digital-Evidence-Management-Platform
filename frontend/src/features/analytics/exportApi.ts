// features/analytics/exportApi.ts
import { getAccessToken } from "@/lib/auth";

const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function downloadServerExport(
  path: "incidents" | "analytics-summary",
  params: { days: number; cameraId?: string },
): Promise<void> {
  const token = getAccessToken();
  if (!token) throw new Error("Not authenticated");

  const q = new URLSearchParams({ days: String(params.days) });
  if (params.cameraId) q.set("cameraId", params.cameraId);

  const res = await fetch(
    `${base}/api/v1/reports/export/${path}?${q}`,
    { headers: { Authorization: `Bearer ${token}` } },
  );

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Export failed (${res.status})`);
  }

  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition");
  const match = cd?.match(/filename="?([^";]+)"?/i);
  const filename = match?.[1] ?? `${path}-export.csv`;

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}