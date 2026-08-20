// SPDX-License-Identifier: Apache-2.0

import { apiFetch } from "@/lib/api"

export interface AppSettings {
  telemetry_enabled: boolean
}

export async function getSettings(): Promise<AppSettings> {
  return apiFetch<AppSettings>("/settings")
}

export async function updateSettings(patch: Partial<AppSettings>): Promise<AppSettings> {
  return apiFetch<AppSettings>("/settings", {
    method: "PATCH",
    body: JSON.stringify(patch),
  })
}
