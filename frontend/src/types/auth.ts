export type LoginRequest = {
  identifier: string
  password: string
}

export type AuthUser = {
  id: string
  email: string
  username: string
  firstName: string
  lastName: string
  mfaEnabled: boolean
  roles: string[]
  permissions: string[]
}

export type AuthTokens = {
  accessToken: string
  refreshToken: string
  tokenType: string
  accessTokenExpiresAt: string
  refreshTokenExpiresAt: string
}

export type LoginSuccessResponse = {
  user: AuthUser
  tokens: AuthTokens
}

export type MfaChallengeResponse = {
  mfaRequired: true
  challengeId: string
  expiresAt: string
  message: string
}

export type LoginResponse = LoginSuccessResponse | MfaChallengeResponse

export function isMfaChallenge(
  data: LoginResponse,
): data is MfaChallengeResponse {
  return "mfaRequired" in data && data.mfaRequired === true
}