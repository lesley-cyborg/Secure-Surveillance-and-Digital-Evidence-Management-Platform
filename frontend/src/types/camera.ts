export type CameraStatus = "ONLINE" | "OFFLINE" | "DEGRADED" | "DISABLED" | string;

export type Camera = {
  id: string;
  siteId: string;
  name: string;
  cameraCode: string;
  ipAddress: string;
  protocol: string;
  status: CameraStatus;
  locationDescription?: string | null;
  isActive: boolean;
  lastSeenAt?: string | null;
  createdAt?: string;
  updatedAt?: string;
};

export type CameraCreateInput = {
  siteId: string;
  name: string;
  cameraCode: string;
  ipAddress: string;
  protocol: "RTSP" | "ONVIF" | "HTTPS";
  streamUrl: string;
  credentialsSecretRef: string;
  locationDescription?: string | null;
  status?: CameraStatus;
  isActive?: boolean;
};

export type CameraListResponse = {
  items: Camera[];
  total: number;
};

export type CameraTestResponse = {
  cameraId: string;
  reachable: boolean;
  latencyMs?: number | null;
  message: string;
  checkedStatus?: CameraStatus | null;
};