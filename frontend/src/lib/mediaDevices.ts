export type VideoDevice = {
  deviceId: string;
  label: string;
};

export async function listVideoDevices(): Promise<VideoDevice[]> {
  if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
    throw new Error("Camera API is not available in this browser");
  }

  // Labels are often empty until permission is granted once
  const warm = await navigator.mediaDevices.getUserMedia({
    video: true,
    audio: false,
  });
  warm.getTracks().forEach((t) => t.stop());

  const devices = await navigator.mediaDevices.enumerateDevices();
  return devices
    .filter((d) => d.kind === "videoinput")
    .map((d, i) => ({
      deviceId: d.deviceId,
      label: d.label?.trim() || `Camera ${i + 1}`,
    }));
}

export async function openWebcam(deviceId?: string): Promise<MediaStream> {
  if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
    throw new Error("Camera API is not available in this browser");
  }

  return navigator.mediaDevices.getUserMedia({
    audio: false,
    video: deviceId
      ? { deviceId: { exact: deviceId }, width: { ideal: 1280 }, height: { ideal: 720 } }
      : { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } },
  });
}

export function stopMediaStream(stream: MediaStream | null): void {
  if (!stream) return;
  stream.getTracks().forEach((t) => t.stop());
}

export function mediaErrorMessage(err: unknown): string {
  if (!(err instanceof Error)) return "Could not access the camera";
  const name = err.name;
  if (name === "NotFoundError" || name === "DevicesNotFoundError") {
    return "No camera is plugged in or available on this workstation";
  }
  if (name === "NotAllowedError" || name === "PermissionDeniedError") {
    return "Camera permission was denied. Allow access in the browser settings";
  }
  if (name === "NotReadableError" || name === "TrackStartError") {
    return "Camera is already in use by another application";
  }
  if (name === "OverconstrainedError") {
    return "Selected camera does not support the requested settings";
  }
  return err.message || "Could not access the camera";
}