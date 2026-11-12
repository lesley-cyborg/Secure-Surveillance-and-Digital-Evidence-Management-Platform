import type { AuthTokens, AuthUser } from "@/types/auth"

const ACCESS_KEY = "ssp_access_token"
const REFRESH_KEY = "ssp_refresh_token"
const USER_KEY = "ssp_user"

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null
  
  // Check primary session storage key, then fallback to common local storage keys
  return (
    sessionStorage.getItem(ACCESS_KEY) ||
    localStorage.getItem("accessToken") ||
    localStorage.getItem("ssp_access_token") ||
    null
  )
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null
  
  return (
    sessionStorage.getItem(REFRESH_KEY) ||
    localStorage.getItem("refreshToken") ||
    localStorage.getItem("ssp_refresh_token") ||
    null
  )
}

export function getStoredUser(): AuthUser | null {
  if (typeof window === "undefined") return null
  
  const raw = sessionStorage.getItem(USER_KEY) || localStorage.getItem("ssp_user")
  if (!raw) return null
  
  try {
    return JSON.parse(raw) as AuthUser
  } catch {
    return null
  }
}

export function setSession(user: AuthUser, tokens: AuthTokens) {
  // Save to both to ensure compatibility
  sessionStorage.setItem(ACCESS_KEY, tokens.accessToken)
  sessionStorage.setItem(REFRESH_KEY, tokens.refreshToken)
  sessionStorage.setItem(USER_KEY, JSON.stringify(user))
  
  localStorage.setItem("accessToken", tokens.accessToken)
  localStorage.setItem("ssp_access_token", tokens.accessToken)
  localStorage.setItem("ssp_user", JSON.stringify(user))
}

export function clearSession() {
  sessionStorage.removeItem(ACCESS_KEY)
  sessionStorage.removeItem(REFRESH_KEY)
  sessionStorage.removeItem(USER_KEY)
  
  localStorage.removeItem("accessToken")
  localStorage.removeItem("ssp_access_token")
  localStorage.removeItem("ssp_user")
  localStorage.removeItem("refreshToken")
}