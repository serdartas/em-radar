import { apiFetch } from "@/lib/api"

export interface SourceConnection {
  id: string
  connector_name: string
  config: Record<string, unknown>
  selected_project_ids: string[]
  selected_board_ids: string[]
  selected_repository_ids: string[]
  created_at: string
}

export interface ConnectionTestResult {
  ok: boolean
  detail: string
  user_display_name: string | null
  permissions: string[]
}

export interface ConnectionDraft {
  connector_name: string
  config: Record<string, unknown>
}

export async function listConnections(): Promise<SourceConnection[]> {
  return apiFetch<SourceConnection[]>("/connections")
}

export async function createConnection(draft: ConnectionDraft): Promise<SourceConnection> {
  return apiFetch<SourceConnection>("/connections", {
    method: "POST",
    body: JSON.stringify(draft),
  })
}

export async function updateConnection(
  id: string,
  draft: ConnectionDraft,
): Promise<SourceConnection> {
  return apiFetch<SourceConnection>(`/connections/${id}`, {
    method: "PATCH",
    body: JSON.stringify(draft),
  })
}

export async function deleteConnection(id: string): Promise<void> {
  await apiFetch<void>(`/connections/${id}`, { method: "DELETE" })
}

export async function testConnectionDraft(draft: ConnectionDraft): Promise<ConnectionTestResult> {
  return apiFetch<ConnectionTestResult>("/connections/test", {
    method: "POST",
    body: JSON.stringify(draft),
  })
}

export async function testExistingConnection(id: string): Promise<ConnectionTestResult> {
  return apiFetch<ConnectionTestResult>(`/connections/${id}/test`, { method: "POST" })
}
