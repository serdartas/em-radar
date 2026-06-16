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

export type BoardType = "kanban" | "other" | "scrum"
export type SprintState = "active" | "closed" | "future"

export interface JiraProject {
  id: string
  external_id: string
  key: string
  name: string
}

export interface JiraBoard {
  id: string
  external_id: string
  project_id: string
  name: string
  type: BoardType | null
}

export interface JiraSprint {
  id: string
  external_id: string
  board_id: string
  name: string
  state: SprintState
  start_date: string | null
  end_date: string | null
  complete_date: string | null
  goal: string | null
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

export async function listJiraProjects(connectionId: string): Promise<JiraProject[]> {
  return apiFetch<JiraProject[]>(`/connections/${connectionId}/projects`)
}

export async function listJiraBoards(
  connectionId: string,
  projectExternalId: string,
): Promise<JiraBoard[]> {
  return apiFetch<JiraBoard[]>(
    `/connections/${connectionId}/projects/${encodeURIComponent(projectExternalId)}/boards`,
  )
}

export async function listJiraSprints(
  connectionId: string,
  boardExternalId: string,
): Promise<JiraSprint[]> {
  return apiFetch<JiraSprint[]>(
    `/connections/${connectionId}/boards/${encodeURIComponent(boardExternalId)}/sprints`,
  )
}
