export type CameraStatus = "ONLINE" | "OFFLINE" | "DEGRADED" | "DISABLED";

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