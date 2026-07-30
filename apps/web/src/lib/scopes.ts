import { apiFetch } from "@/lib/api"

export interface ScopeDefinition {
  id: string
  connection_id: string
  name: string
  scope_type: "board" | "custom" | "project" | "repository" | "saved_filter"
  external_ref: Record<string, string | null>
  capabilities: string[]
  created_at: string
  updated_at: string
}

export interface ScopeDefinitionCreate {
  connection_id: string
  name: string
  scope_type: "board" | "custom" | "project" | "repository" | "saved_filter"
  external_ref: Record<string, string>
  capabilities: string[]
}

export async function listScopes(): Promise<ScopeDefinition[]> {
  return apiFetch<ScopeDefinition[]>("/scopes")
}

export async function createScope(draft: ScopeDefinitionCreate): Promise<ScopeDefinition> {
  return apiFetch<ScopeDefinition>("/scopes", {
    method: "POST",
    body: JSON.stringify(draft),
  })
}
