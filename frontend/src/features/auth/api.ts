import { apiRequest } from "@/lib/api"
import type { LoginRequest, LoginResponse } from "@/types/auth"

export async function loginRequest(body: LoginRequest): Promise<{
  status: number
  data: LoginResponse
}> {
  const API_BASE_URL =
    process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"

  const response = await fetch(`${API_BASE_URL}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })

  const data = (await response.json()) as LoginResponse

  if (response.status === 200 || response.status === 202) {
    return { status: response.status, data }
  }

  // normalize error
  const detail = (data as { detail?: unknown }).detail
  let message = `Login failed (${response.status})`
  if (typeof detail === "string") message = detail
  else if (detail && typeof detail === "object" && "message" in detail) {
    message = String((detail as { message: string }).message)
  }
  throw new Error(message)
}