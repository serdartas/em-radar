import { apiFetch } from "@/lib/api"
import type { Severity } from "@/lib/severity"

export interface ReportSettings {
  severity: Severity
  category: string
  message_template?: string | null
}

export interface SignalTemplate {
  key: string
  name: string
  description: string
  required_connector_type: string
  entity_type: string
  required_scope_capabilities: string[]
  expression: Record<string, unknown>
  report_settings: ReportSettings
}

export interface SignalDefinition {
  id: string
  name: string
  description: string | null
  entity_type: string
  target_scopes: Array<{ connector_id: string; scope_id: string; scope_type: string }>
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
  target_scopes: Array<{ connector_id: string; scope_id: string; scope_type: string }>
  expression: Record<string, unknown>
  report_settings: ReportSettings
  enabled: boolean
  origin: "system_template" | "user_created" | "imported"
  template_key?: string | null
}

export async function listSignalTemplates(): Promise<SignalTemplate[]> {
  return apiFetch<SignalTemplate[]>("/signal-templates")
}

export async function restoreSignalTemplate(templateKey: string): Promise<SignalTemplate> {
  return apiFetch<SignalTemplate>(`/signal-templates/${templateKey}/restore`, { method: "POST" })
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
