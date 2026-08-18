// SPDX-License-Identifier: Apache-2.0

import { apiFetch } from "@/lib/api"

export interface SignalConfigGroup {
  id: string
  name: string
  description: string | null
  signal_ids: string[]
  created_at: string
  updated_at: string
}

export interface SignalConfigGroupCreate {
  name: string
  description?: string | null
  signal_ids?: string[]
}

export interface SignalConfigGroupUpdate {
  name?: string
  description?: string | null
  signal_ids?: string[]
}

export async function listSignalConfigGroups(): Promise<SignalConfigGroup[]> {
  return apiFetch<SignalConfigGroup[]>("/signal-config-groups")
}

export async function createSignalConfigGroup(
  group: SignalConfigGroupCreate,
): Promise<SignalConfigGroup> {
  return apiFetch<SignalConfigGroup>("/signal-config-groups", {
    method: "POST",
    body: JSON.stringify(group),
  })
}

export async function updateSignalConfigGroup(
  id: string,
  group: SignalConfigGroupUpdate,
): Promise<SignalConfigGroup> {
  return apiFetch<SignalConfigGroup>(`/signal-config-groups/${id}`, {
    method: "PATCH",
    body: JSON.stringify(group),
  })
}

export async function deleteSignalConfigGroup(id: string): Promise<void> {
  return apiFetch<void>(`/signal-config-groups/${id}`, { method: "DELETE" })
}
