import type { AuthTokens, AuthUser } from "@/types/auth"

const ACCESS_KEY = "ssp_access_token"
const REFRESH_KEY = "ssp_refresh_token"
const USER_KEY = "ssp_user"

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null
  return sessionStorage.getItem(ACCESS_KEY)
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null
  return sessionStorage.getItem(REFRESH_KEY)
}

export function getStoredUser(): AuthUser | null {
  if (typeof window === "undefined") return null
  const raw = sessionStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as AuthUser
  } catch {
    return null
  }
}

export function setSession(user: AuthUser, tokens: AuthTokens) {
  sessionStorage.setItem(ACCESS_KEY, tokens.accessToken)
  sessionStorage.setItem(REFRESH_KEY, tokens.refreshToken)
  sessionStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function clearSession() {
  sessionStorage.removeItem(ACCESS_KEY)
  sessionStorage.removeItem(REFRESH_KEY)
  sessionStorage.removeItem(USER_KEY)
}