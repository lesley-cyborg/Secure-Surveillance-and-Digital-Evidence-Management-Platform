import { getAccessToken } from "@/lib/auth";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"

type ApiErrorBody = {
  detail?: string | { code?: string; message?: string }
  message?: string
}

export class ApiRequestError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = "ApiRequestError"
    this.status = status
  }
}

function messageFromErrorBody(error: ApiErrorBody, status: number): string {
  if (typeof error.detail === "string") return error.detail
  if (error.detail && typeof error.detail === "object") {
    return error.detail.message ?? error.detail.code ?? `Request failed (${status})`
  }
  if (error.message) return error.message
  return `Request failed with status ${status}`
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = typeof window !== "undefined" ? getAccessToken() : null;

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { "Authorization": `Bearer ${token}` } : {}),
      ...(options.headers ?? {}),
    },
  });

  // Login may return 202 with a body (MFA)
  const isJson = (response.headers.get("content-type") ?? "").includes(
    "application/json",
  )

  if (!response.ok && response.status !== 202) {
    let message = `Request failed with status (${response.status})`;
    if (isJson) {
      try {
        const error = (await response.json()) as ApiErrorBody
        message = messageFromErrorBody(error, response.status)
      } catch {
        /* keep generic */
      }
    }
    throw new ApiRequestError(message, response.status)
  }

  if (response.status === 204) return undefined as T; 
  return response.json() as Promise<T>;
}

export { API_BASE_URL }