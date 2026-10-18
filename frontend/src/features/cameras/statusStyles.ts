import type { CameraStatus } from "@/types/camera";

export function statusDotClass(status: CameraStatus): string {
  switch (status) {
    case "ONLINE":
      return "bg-emerald-400";
    case "DEGRADED":
      return "bg-amber-400";
    case "DISABLED":
      return "bg-zinc-600";
    default:
      return "bg-zinc-500";
  }
}

export function statusTextClass(status: CameraStatus): string {
  switch (status) {
    case "ONLINE":
      return "text-emerald-400";
    case "DEGRADED":
      return "text-amber-400";
    default:
      return "text-zinc-400";
  }
}

export function formatLastSeen(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return "—";
  }
}