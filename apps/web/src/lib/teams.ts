// SPDX-License-Identifier: Apache-2.0

import { apiFetch } from "@/lib/api"

export type WorkingMode = "kanban" | "scrum"

export type GitLabConfigStatus = "not_applicable" | "setup_required" | "configured"

export interface TeamProfile {
  id: string
  name: string
  description: string | null
  connection_ids: string[]
  scope_ids: string[]
  signal_config_group_ids: string[]
  code_connection_id: string | null
  working_mode: WorkingMode
  sprint_length_days: number | null
  member_user_keys: string[]
  gitlab_config_status: GitLabConfigStatus
  created_at: string
  updated_at: string
}

export interface TeamProfileCreate {
  name: string
  description?: string | null
  connection_ids?: string[]
  scope_ids?: string[]
  signal_config_group_ids?: string[]
  code_connection_id?: string | null
  working_mode?: WorkingMode
  sprint_length_days?: number | null
}

export interface TeamProfileUpdate {
  name?: string
  description?: string | null
  connection_ids?: string[]
  scope_ids?: string[]
  signal_config_group_ids?: string[]
  code_connection_id?: string | null
  working_mode?: WorkingMode
  sprint_length_days?: number | null
}

/** A team with no board scope and no code connection has no sources and cannot run a report. */
export function teamHasNoSources(team: TeamProfile): boolean {
  return team.scope_ids.length === 0 && !team.code_connection_id
}

export async function listTeams(): Promise<TeamProfile[]> {
  return apiFetch<TeamProfile[]>("/teams")
}

export async function createTeam(team: TeamProfileCreate): Promise<TeamProfile> {
  return apiFetch<TeamProfile>("/teams", { method: "POST", body: JSON.stringify(team) })
}

export async function updateTeam(id: string, team: TeamProfileUpdate): Promise<TeamProfile> {
  return apiFetch<TeamProfile>(`/teams/${id}`, { method: "PATCH", body: JSON.stringify(team) })
}

export async function deleteTeam(id: string): Promise<void> {
  return apiFetch<void>(`/teams/${id}`, { method: "DELETE" })
}
