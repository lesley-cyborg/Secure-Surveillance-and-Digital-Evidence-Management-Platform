import { apiRequest } from "@/lib/api";
import type { Camera, CameraListResponse, CameraTestResponse, CameraCreateInput } from "@/types/camera";

export async function listCameras(): Promise<Camera[]> {
  const data = await apiRequest<CameraListResponse>("/api/v1/cameras");
  return data.items ?? [];
}

export async function createCamera(input: CameraCreateInput): Promise<Camera> {
  return apiRequest<Camera>("/api/v1/cameras", {
    method: "POST",
    body: JSON.stringify({
      siteId: input.siteId,
      name: input.name,
      cameraCode: input.cameraCode,
      ipAddress: input.ipAddress,
      protocol: input.protocol,
      streamUrl: input.streamUrl,
      credentialsSecretRef: input.credentialsSecretRef,
      locationDescription: input.locationDescription ?? null,
      status: input.status ?? "OFFLINE",
      isActive: input.isActive ?? true,
    }),
  });
}

export async function getCamera(id: string): Promise<Camera> {
  return apiRequest<Camera>(`/api/v1/cameras/${id}`);
}

export async function testCamera(id: string): Promise<CameraTestResponse> {
  return apiRequest<CameraTestResponse>(`/api/v1/cameras/${id}/test`, {
    method: "POST",
  });
}

export async function listCamerasPage(): Promise<CameraListResponse> {
  return apiRequest<CameraListResponse>("/api/v1/cameras");
}