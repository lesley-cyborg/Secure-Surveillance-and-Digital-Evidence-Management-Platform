import { listCameras } from "@/features/cameras/api";
import { listCustodyEvents } from "@/features/custody/api";
import { listEvidence } from "@/features/evidence/api";
import { listIncidents } from "@/features/incidents/api";
import type { Camera } from "@/types/camera";
import type { Incident } from "@/types/incident";

export type DashboardStats = {
  camerasTotal: number;
  camerasOnline: number;
  incidentsTotal: number;
  incidentsOpen: number;
  evidenceTotal: number;
  recentIncidents: Incident[];
  /** Last 7 days: ISO date (yyyy-mm-dd) → count */
  incidentsByDay: { date: string; label: string; count: number }[];
  /** Sampled from recent evidence custody timelines */
  custodyEventsSampled: number;
  custodyEvidenceSampled: number;
};

function isCameraOnline(status: string | undefined): boolean {
  const s = (status ?? "").toUpperCase();
  return s === "ONLINE" || s === "ACTIVE";
}

function isIncidentOpen(status: string | undefined): boolean {
  const s = (status ?? "").toUpperCase();
  return (
    s === "NEW" ||
    s === "OPEN" ||
    s === "CONFIRMED" ||
    s === "INVESTIGATING" ||
    s === "ACTIVE"
  );
}

function dayKey(iso: string): string {
  return iso.slice(0, 10); // yyyy-mm-dd from ISO
}

function buildIncidentsByDay(
  incidents: Incident[],
  days = 7,
): { date: string; label: string; count: number }[] {
  const now = new Date();
  const keys: string[] = [];
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    keys.push(d.toISOString().slice(0, 10));
  }
  const counts = new Map(keys.map((k) => [k, 0]));
  for (const inc of incidents) {
    const raw = inc.detectedAt || inc.createdAt;
    if (!raw) continue;
    const k = dayKey(raw);
    if (counts.has(k)) counts.set(k, (counts.get(k) ?? 0) + 1);
  }
  return keys.map((date) => ({
    date,
    label: date.slice(5), // MM-DD
    count: counts.get(date) ?? 0,
  }));
}

export async function loadDashboardStats(): Promise<DashboardStats> {
  const [cameraList, incidents, evidence] = await Promise.all([
    listCameras().catch((): Camera[] => []),
    listIncidents({ limit: 100 }).catch(() => ({
      items: [] as Incident[],
      total: 0,
    })),
    listEvidence({ limit: 50 }).catch(() => ({
      items: [] as { id: string }[],
      total: 0,
    })),
  ]);

  const incidentItems = incidents.items ?? [];
  const evidenceItems = evidence.items ?? [];
  const evidenceTotal = evidence.total ?? evidenceItems.length;

  // Sample custody events from up to 5 recent evidence rows
  const sample = evidenceItems.slice(0, 5);
  let custodyEventsSampled = 0;
  await Promise.all(
    sample.map(async (ev) => {
      try {
        const data = await listCustodyEvents(ev.id, 1, 25);
        custodyEventsSampled += data.items?.length ?? 0;
      } catch {
        /* ignore single failure */
      }
    }),
  );

  return {
    camerasTotal: cameraList.length,
    camerasOnline: cameraList.filter((c) => isCameraOnline(c.status)).length,
    incidentsTotal: incidents.total ?? incidentItems.length,
    incidentsOpen: incidentItems.filter((i) => isIncidentOpen(i.status)).length,
    evidenceTotal,
    recentIncidents: incidentItems.slice(0, 8),
    incidentsByDay: buildIncidentsByDay(incidentItems, 7),
    custodyEventsSampled,
    custodyEvidenceSampled: sample.length,
  };
}