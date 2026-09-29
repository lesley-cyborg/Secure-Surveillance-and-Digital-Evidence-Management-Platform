const KEY = "ssp_access_token";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(KEY);
}

export function setAccessToken(token: string) {
  sessionStorage.setItem(KEY, token);
}

export function clearAccessToken() {
  sessionStorage.removeItem(KEY);
}