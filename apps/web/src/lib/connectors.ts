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

export interface SignalValueProvider {
  type: string
  source: string
  depends_on: string[]
}

export interface SignalFieldAvailability {
  requires_scope_capability: string[]
}

export interface SignalField {
  key: string
  label: string
  type: string
  operators: string[]
  values: unknown[]
  value_provider: SignalValueProvider | null
  availability: SignalFieldAvailability | null
}

export interface SignalCapabilitySchema {
  connector_type: string
  entity_types: string[]
  scope_types: Array<{ key: string; label: string; capabilities: string[] }>
  fields: SignalField[]
}

export interface Connector {
  name: string
  display_name: string
  config_schema: JsonSchema
  capabilities: ConnectorCapabilities
  signal_schema?: SignalCapabilitySchema
}

export async function getConnectors(): Promise<Connector[]> {
  return apiFetch<Connector[]>("/connectors")
}
