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

export async function listScopes(): Promise<ScopeDefinition[]> {
  return apiFetch<ScopeDefinition[]>("/scopes")
}
