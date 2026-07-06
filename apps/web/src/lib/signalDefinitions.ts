import { apiFetch } from "@/lib/api"
import type { Severity } from "@/lib/severity"

export interface ReportSettings {
  severity: Severity
  category: string
  message_template?: string | null
}

export interface SignalDefinition {
  id: string
  name: string
  description: string | null
  entity_type: string
  expression: Record<string, unknown>
  report_settings: ReportSettings
  enabled: boolean
  origin: "system_template" | "user_created" | "imported"
  template_key: string | null
  version: number
  created_at: string
  updated_at: string
}

export interface SignalDefinitionCreate {
  name: string
  description?: string | null
  entity_type: string
  expression: Record<string, unknown>
  report_settings: ReportSettings
  enabled: boolean
  origin: "system_template" | "user_created" | "imported"
  template_key?: string | null
}

export interface SignalDefinitionPreviewSample {
  item_key: string
  title: string
  reason: string
  evidence: Record<string, unknown>
}

export interface SignalDefinitionPreview {
  match_count: number
  samples: SignalDefinitionPreviewSample[]
  warnings: string[]
}

export async function listSignalDefinitions(): Promise<SignalDefinition[]> {
  return apiFetch<SignalDefinition[]>("/signal-definitions")
}

export async function createSignalDefinition(
  definition: SignalDefinitionCreate,
): Promise<SignalDefinition> {
  return apiFetch<SignalDefinition>("/signal-definitions", {
    method: "POST",
    body: JSON.stringify(definition),
  })
}

export async function previewSignalDefinition(
  definition: SignalDefinitionCreate,
): Promise<SignalDefinitionPreview> {
  return apiFetch<SignalDefinitionPreview>("/signal-definitions/preview", {
    method: "POST",
    body: JSON.stringify(definition),
  })
}

export async function updateSignalDefinition(
  id: string,
  definition: Partial<SignalDefinitionCreate>,
): Promise<SignalDefinition> {
  return apiFetch<SignalDefinition>(`/signal-definitions/${id}`, {
    method: "PATCH",
    body: JSON.stringify(definition),
  })
}

export async function deleteSignalDefinition(id: string): Promise<void> {
  return apiFetch<void>(`/signal-definitions/${id}`, { method: "DELETE" })
}
