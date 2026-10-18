import { getStoredUser } from "@/lib/auth";

export function hasPermission(code: string): boolean {
  const user = getStoredUser();
  const perms = user?.permissions ?? [];
  return perms.includes(code);
}

export function canCreateCameras(): boolean {
  return hasPermission("cameras.create");
}

export function canTestCameras(): boolean {
  return hasPermission("cameras.test");
}

export function currentUserId(): string | null {
  const user = getStoredUser();
  return user?.id ?? null;
}

export function canDownloadEvidence(): boolean {
  return hasPermission("evidence.content.read");
}

export function canVerifyEvidence(): boolean {
  return hasPermission("evidence.verify");
}

/** Align codes with your roles table if names differ */
export function canInitiateCustodyTransfer(): boolean {
  return (
    hasPermission("custody.transfer") ||
    hasPermission("custody.create") ||
    hasPermission("evidence.transfer")
  );
}

export function canAcceptCustodyTransfer(): boolean {
  return (
    hasPermission("custody.transfer.accept") ||
    hasPermission("custody.transfer")
  );
}

export function canRejectCustodyTransfer(): boolean {
  return (
    hasPermission("custody.transfer.reject") ||
    hasPermission("custody.transfer")
  );
}

/** Report / analytics export (match your roles table) */
export function canExportReports(): boolean {
  return (
    hasPermission("reports.export") ||
    hasPermission("reports.generate") ||
    hasPermission("analytics.export")
  );
}