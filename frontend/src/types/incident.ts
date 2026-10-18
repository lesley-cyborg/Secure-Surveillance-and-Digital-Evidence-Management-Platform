export type IncidentSourceType = "AI" | "MANUAL" | string;
export type IncidentStatus = "NEW" | "OPEN" | "CONFIRMED" | "ASSIGNED" | "FALSE_POSITIVE" | "INVESTIGATING" | "ESCALATED" | "RESOLVED" | "REOPENED" | "CLOSED";
export type Severity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type Priority = "LOW" | "NORMAL" | "HIGH" | "URGENT";

export type Incident = {
  id: string;
  incidentNumber: string;
  primaryCameraId: string | null;
  sourceType: IncidentSourceType;
  incidentType: string;
  severity: Severity;
  priority: Priority;
  status: IncidentStatus;
  title: string;
  description: string | null;
  disposition: string | null;
  detectedAt: string;
  confirmedAt: string | null;
  closedAt: string | null;
  createdAt: string;
  updatedAt: string;
};

export type IncidentSummary = Incident;

export type IncidentListResponse = {
  items: Incident[];
  total: number;
};