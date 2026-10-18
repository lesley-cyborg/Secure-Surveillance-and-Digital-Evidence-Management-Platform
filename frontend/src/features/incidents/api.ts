import { apiRequest } from "@/lib/api";
import type { Incident, IncidentListResponse } from "@/types/incident";

export async function listIncidents(params?: {
  limit?: number;
}): Promise<IncidentListResponse> {
  const q = new URLSearchParams();
  if (params?.limit != null) q.set("limit", String(params.limit));
  const qs = q.toString();

  const data = await apiRequest<IncidentListResponse | Incident[]>(
    `/api/v1/incidents${qs ? `?${qs}` : ""}`,
  );

  if (Array.isArray(data)) {
    return { items: data, total: data.length };
  }

  return {
    items: data.items ?? [],
    total: data.total ?? data.items?.length ?? 0,
  };
}

export async function getIncident(id: string): Promise<Incident> {
  return apiRequest<Incident>(`/api/v1/incidents/${id}`);
}