// SPDX-License-Identifier: Apache-2.0

import { apiFetch } from "@/lib/api"

export type DateFormat = "dd/mm/yyyy" | "mm/dd/yyyy" | "yyyy-mm-dd"

export const DATE_FORMAT_OPTIONS: { label: string; value: DateFormat }[] = [
  { value: "dd/mm/yyyy", label: "DD/MM/YYYY" },
  { value: "mm/dd/yyyy", label: "MM/DD/YYYY" },
  { value: "yyyy-mm-dd", label: "YYYY-MM-DD" },
]

export interface AppSettings {
  telemetry_enabled: boolean
  date_format: DateFormat
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
