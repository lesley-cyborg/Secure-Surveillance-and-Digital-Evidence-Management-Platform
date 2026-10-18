const DASHBOARD_AUTO_REFRESH_KEY = "ssp_dashboard_auto_refresh";

export function getDashboardAutoRefresh(): boolean {
  if (typeof window === "undefined") return true;
  const v = localStorage.getItem(DASHBOARD_AUTO_REFRESH_KEY);
  if (v === null) return true;
  return v === "true";
}

export function setDashboardAutoRefresh(enabled: boolean): void {
  localStorage.setItem(DASHBOARD_AUTO_REFRESH_KEY, String(enabled));
}