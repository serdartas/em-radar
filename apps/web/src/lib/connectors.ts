import { apiFetch } from "@/lib/api"
import type { JsonSchema } from "@/lib/jsonSchema"

export interface ConnectorCapabilities {
  provides_workitems: boolean
  provides_sprints: boolean
  provides_mergerequests: boolean
  provides_repositories: boolean
  provides_reviews: boolean
  provides_comments: boolean
  provides_transitions: boolean
  supports_incremental_fetch: boolean
  supports_pagination_cursor: boolean
  max_window_days: number | null
}

export interface Connector {
  name: string
  display_name: string
  config_schema: JsonSchema
  capabilities: ConnectorCapabilities
}

export async function getConnectors(): Promise<Connector[]> {
  return apiFetch<Connector[]>("/connectors")
}
