import type { AnalyticsBundle } from "./api";

function escapeCell(value: string | number | null | undefined): string {
  const s = value == null ? "" : String(value);
  if (/[",\n\r]/.test(s)) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

function toCsv(rows: (string | number | null | undefined)[][]): string {
  return rows.map((row) => row.map(escapeCell).join(",")).join("\r\n");
}

export function buildAnalyticsCsv(data: AnalyticsBundle): string {
  const sections: string[] = [];

  sections.push(
    toCsv([
      ["section", "metric", "value"],
      ["summary", "range_days", data.rangeDays],
      ["summary", "camera_filter", data.cameraId ?? "ALL"],
      ["summary", "incidents_in_range", data.incidentsFiltered.length],
      ["summary", "open_in_range", data.openCount],
      ["summary", "cameras_total", data.cameras.length],
      ["summary", "evidence_loaded", data.evidence.length],
      ["summary", "custody_events_sampled", data.custodyEventsSampled],
      ["summary", "custody_evidence_sampled", data.custodyEvidenceSampled],
    ]),
  );

  sections.push(
    "\r\n" +
      toCsv([
        ["trend_date", "count"],
        ...data.trend.map((p) => [p.date, p.count]),
      ]),
  );

  sections.push(
    "\r\n" +
      toCsv([
        ["status", "count"],
        ...data.byStatus.map((p) => [p.name, p.count]),
      ]),
  );

  sections.push(
    "\r\n" +
      toCsv([
        ["severity", "count"],
        ...data.bySeverity.map((p) => [p.name, p.count]),
      ]),
  );

  sections.push(
    "\r\n" +
      toCsv([
        ["source", "count"],
        ...data.bySource.map((p) => [p.name, p.count]),
      ]),
  );

  sections.push(
    "\r\n" +
      toCsv([
        ["incident_id", "incident_number", "title", "status", "severity", "source", "type", "detected_at"],
        ...data.incidentsFiltered.map((i) => [
          i.id,
          i.incidentNumber,
          i.title,
          i.status,
          i.severity,
          i.sourceType,
          i.incidentType,
          i.detectedAt ?? i.createdAt,
        ]),
      ]),
  );

  return sections.join("\r\n");
}

export function downloadCsv(filename: string, content: string): void {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
