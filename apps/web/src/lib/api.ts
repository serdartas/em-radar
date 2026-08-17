// SPDX-License-Identifier: Apache-2.0

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "/api").replace(/\/$/, "")

export class ApiError extends Error {
  readonly status: number
  readonly detail: unknown

  constructor(status: number, message: string, detail: unknown = null) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.detail = detail
  }
}

interface FastApiErrorBody {
  detail?: unknown
}

function extractMessage(body: unknown): string | null {
  if (typeof body !== "object" || body === null) {
    return null
  }
  const detail = (body as FastApiErrorBody).detail
  if (typeof detail === "string") {
    return detail
  }
  if (typeof detail === "object" && detail !== null && "message" in detail) {
    const message = (detail as { message: unknown }).message
    if (typeof message === "string") {
      return message
    }
  }
  return null
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  })

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const message =
      extractMessage(body) ?? `Request to ${path} failed with status ${response.status}.`
    const detail = (body as FastApiErrorBody | null)?.detail ?? body
    throw new ApiError(response.status, message, detail)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}

export function apiErrorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback
}
