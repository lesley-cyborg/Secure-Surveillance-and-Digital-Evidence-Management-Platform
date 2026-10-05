import { apiRequest } from "@/lib/api";
import type { Camera, CameraListResponse, CameraTestResponse } from "@/types/camera";

export async function listCameras(): Promise<Camera[]> {
  const data = await apiRequest<CameraListResponse>("/api/v1/cameras");
  return data.items ?? [];
}

export async function getCamera(id: string): Promise<Camera> {
  return apiRequest<Camera>(`/api/v1/cameras/${id}`);
}

export async function testCamera(id: string): Promise<CameraTestResponse> {
  return apiRequest<CameraTestResponse>(`/api/v1/cameras/${id}/test`, {
    method: "POST",
  });
}