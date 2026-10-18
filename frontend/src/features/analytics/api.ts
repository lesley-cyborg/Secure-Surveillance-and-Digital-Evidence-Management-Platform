import { listCameras } from "@/features/cameras/api";
import { listCustodyEvents } from "@/features/custody/api";
import { listEvidence } from "@/features/evidence/api";
import { listIncidents } from "@/features/incidents/api";
import type { Camera } from "@/types/camera";
import type { Evidence } from "@/types/evidence";
import type { Incident } from "@/types/incident";
import {
  cameraHealth,
  evidenceByStatus,
  evidenceByType,
  filterIncidents,
  highSeverityRecent,
  incidentsByDay,
  groupCount,
  topIncidentTypes,
  type DayPoint,
  type NamedCount,
  type RangeDays,
} from "./aggregate";

export type AnalyticsBundle = {
  rangeDays: RangeDays;
  cameraId: string | null;
  cameras: Camera[];
  incidentsAll: Incident[];
  incidentsFiltered: Incident[];
  evidence: Evidence[];
  trend: DayPoint[];
  byStatus: NamedCount[];
  bySeverity: NamedCount[];
  bySource: NamedCount[];
  cameraHealth: NamedCount[];
  evidenceStatus: NamedCount[];
  evidenceType: NamedCount[];
  topTypes: NamedCount[];
  highSeverity: Incident[];
  custodyEventsSampled: number;
  custodyEvidenceSampled: number;
  openCount: number;
};

function isOpen(status: string | undefined): boolean {
  const s = (status ?? "").toUpperCase();
  return (
    s === "NEW" ||
    s === "OPEN" ||
    s === "CONFIRMED" ||
    s === "INVESTIGATING" ||
    s === "ACTIVE"
  );
}

export async function loadAnalytics(
  rangeDays: RangeDays,
  cameraId: string | null,
): Promise<AnalyticsBundle> {
  const [cameras, incidentsRes, evidenceRes] = await Promise.all([
    listCameras().catch((): Camera[] => []),
    listIncidents({ limit: 200 }).catch(() => ({
      items: [] as Incident[],
      total: 0,
    })),
    listEvidence({ limit: 100 }).catch(() => ({
      items: [] as Evidence[],
      total: 0,
    })),
  ]);

  const incidentsAll = incidentsRes.items ?? [];
  const incidentsFiltered = filterIncidents(incidentsAll, rangeDays, cameraId);
  const evidence = evidenceRes.items ?? [];

  const sample = evidence.slice(0, 5);
  let custodyEventsSampled = 0;
  await Promise.all(
    sample.map(async (ev) => {
      try {
        const data = await listCustodyEvents(ev.id, 1, 25);
        custodyEventsSampled += data.items?.length ?? 0;
      } catch {
        /* ignore */
      }
    }),
  );

  return {
    rangeDays,
    cameraId,
    cameras,
    incidentsAll,
    incidentsFiltered,
    evidence,
    trend: incidentsByDay(incidentsFiltered, rangeDays),
    byStatus: groupCount(incidentsFiltered, (i) => i.status || "UNKNOWN"),
    bySeverity: groupCount(incidentsFiltered, (i) => i.severity || "UNKNOWN"),
    bySource: groupCount(incidentsFiltered, (i) => i.sourceType || "UNKNOWN"),
    cameraHealth: cameraHealth(cameras),
    evidenceStatus: evidenceByStatus(evidence),
    evidenceType: evidenceByType(evidence),
    topTypes: topIncidentTypes(incidentsFiltered),
    highSeverity: highSeverityRecent(incidentsFiltered),
    custodyEventsSampled,
    custodyEvidenceSampled: sample.length,
    openCount: incidentsFiltered.filter((i) => isOpen(i.status)).length,
  };
}