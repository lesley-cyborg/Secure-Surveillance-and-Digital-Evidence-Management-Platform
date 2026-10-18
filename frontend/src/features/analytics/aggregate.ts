import type { Camera } from "@/types/camera";
import type { Evidence } from "@/types/evidence";
import type { Incident } from "@/types/incident";

export type RangeDays = 7 | 14 | 30;

export type DayPoint = { date: string; label: string; count: number };
export type NamedCount = { name: string; count: number };

function dayKey(iso: string): string {
  return iso.slice(0, 10);
}

function inRange(iso: string | null | undefined, days: RangeDays): boolean {
  if (!iso) return false;
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return false;
  const cutoff = Date.now() - days * 24 * 60 * 60 * 1000;
  return t >= cutoff;
}

export function filterIncidents(
  items: Incident[],
  days: RangeDays,
  cameraId?: string | null,
): Incident[] {
  return items.filter((i) => {
    const when = i.detectedAt || i.createdAt;
    if (!inRange(when, days)) return false;
    if (cameraId && i.primaryCameraId !== cameraId) return false;
    return true;
  });
}

export function incidentsByDay(
  items: Incident[],
  days: RangeDays,
): DayPoint[] {
  const keys: string[] = [];
  const now = new Date();
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    keys.push(d.toISOString().slice(0, 10));
  }
  const map = new Map(keys.map((k) => [k, 0]));
  for (const inc of items) {
    const raw = inc.detectedAt || inc.createdAt;
    if (!raw) continue;
    const k = dayKey(raw);
    if (map.has(k)) map.set(k, (map.get(k) ?? 0) + 1);
  }
  return keys.map((date) => ({
    date,
    label: days > 14 ? date.slice(5) : date.slice(5),
    count: map.get(date) ?? 0,
  }));
}

export function groupCount<T>(
  items: T[],
  keyFn: (item: T) => string,
): NamedCount[] {
  const map = new Map<string, number>();
  for (const item of items) {
    const k = keyFn(item) || "UNKNOWN";
    map.set(k, (map.get(k) ?? 0) + 1);
  }
  return [...map.entries()]
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count);
}

export function cameraHealth(cameras: Camera[]): NamedCount[] {
  const map = new Map<string, number>();
  for (const c of cameras) {
    const s = (c.status || "UNKNOWN").toUpperCase();
    map.set(s, (map.get(s) ?? 0) + 1);
  }
  return [...map.entries()].map(([name, count]) => ({ name, count }));
}

export function evidenceByStatus(items: Evidence[]): NamedCount[] {
  return groupCount(items, (e) => String(e.status || "UNKNOWN"));
}

export function evidenceByType(items: Evidence[]): NamedCount[] {
  return groupCount(items, (e) => String(e.evidenceType || "OTHER"));
}

export function topIncidentTypes(items: Incident[], n = 8): NamedCount[] {
  return groupCount(items, (i) => i.incidentType || "UNSPECIFIED").slice(0, n);
}

export function highSeverityRecent(items: Incident[], n = 10): Incident[] {
  const rank = (s: string) => {
    const u = s.toUpperCase();
    if (u === "CRITICAL") return 4;
    if (u === "HIGH") return 3;
    if (u === "MEDIUM") return 2;
    return 1;
  };
  return [...items]
    .sort((a, b) => {
      const dr = rank(b.severity) - rank(a.severity);
      if (dr !== 0) return dr;
      return (
        new Date(b.detectedAt || b.createdAt).getTime() -
        new Date(a.detectedAt || a.createdAt).getTime()
      );
    })
    .slice(0, n);
}