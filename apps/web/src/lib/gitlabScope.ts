// SPDX-License-Identifier: Apache-2.0

import { apiFetch } from "@/lib/api"

/**
 * A user result from the server-side GitLab member search endpoint
 * (GET /api/teams/{teamId}/gitlab/member-search).
 *
 * Field names match the backend MemberSearchResult schema exactly.
 */
export interface GitLabMemberSearchResult {
  provider_user_id: string
  username: string
  display_name: string
  avatar_url: string | null
}

/**
 * A saved GitLab team member returned by the members list/replace endpoints
 * (GET and PUT /api/teams/{teamId}/gitlab/members).
 *
 * Field names match the backend TeamGitLabMemberRead schema exactly.
 */
export interface TeamGitLabMember {
  id: string
  team_profile_id: string
  connection_id: string | null
  gitlab_user_id: number
  username: string
  display_name: string | null
  verification_status: string
  created_at: string
  updated_at: string
}

/**
 * Input element for the PUT /api/teams/{teamId}/gitlab/members endpoint.
 *
 * Field name matches the backend GitLabMemberInput schema exactly.
 */
export interface GitLabMemberInput {
  gitlab_user_id: number
}

/**
 * Server-side search for GitLab users matching `q`.
 *
 * Results are paginated by the server; the caller is responsible for debouncing
 * before invoking this function (§24).
 */
export async function searchGitLabMembers(
  teamId: string,
  q: string,
  limit?: number,
  page?: number,
): Promise<GitLabMemberSearchResult[]> {
  const params = new URLSearchParams({ q })
  if (limit !== undefined) params.set("limit", String(limit))
  if (page !== undefined) params.set("page", String(page))
  return apiFetch<GitLabMemberSearchResult[]>(
    `/teams/${teamId}/gitlab/member-search?${params.toString()}`,
  )
}

/** Fetch the team's currently saved GitLab members. */
export async function listGitLabMembers(teamId: string): Promise<TeamGitLabMember[]> {
  return apiFetch<TeamGitLabMember[]>(`/teams/${teamId}/gitlab/members`)
}

/**
 * Replace the team's GitLab member list with the supplied set (replace
 * semantics — the server validates each id and returns the saved rows).
 */
export async function replaceGitLabMembers(
  teamId: string,
  members: GitLabMemberInput[],
): Promise<TeamGitLabMember[]> {
  return apiFetch<TeamGitLabMember[]>(`/teams/${teamId}/gitlab/members`, {
    method: "PUT",
    body: JSON.stringify(members),
  })
}

// ---------------------------------------------------------------------------
// Repository types and API functions (M9-05 endpoints)
// ---------------------------------------------------------------------------

/**
 * A saved GitLab team repository returned by the repositories list/replace
 * endpoints (GET and PUT /api/teams/{teamId}/gitlab/repositories).
 *
 * Field names match the backend TeamGitLabRepositoryRead schema exactly.
 */
export interface TeamGitLabRepository {
  id: string
  team_profile_id: string
  connection_id: string | null
  gitlab_project_id: number
  name: string
  path_with_namespace: string
  verification_status: string
  created_at: string
  updated_at: string
}

/**
 * Input element for the PUT /api/teams/{teamId}/gitlab/repositories endpoint.
 *
 * Field name matches the backend GitLabRepositoryInput schema exactly.
 */
export interface GitLabRepositoryInput {
  gitlab_project_id: number
}

/**
 * A result from the server-side GitLab project search endpoint
 * (GET /api/teams/{teamId}/gitlab/project-search).
 *
 * Field names match the backend ProjectSearchResult schema exactly.
 */
export interface ProjectSearchResult {
  provider_project_id: string
  name: string
  path_with_namespace: string
}

/**
 * A result from the server-side repository suggestions endpoint
 * (GET /api/teams/{teamId}/gitlab/repository-suggestions).
 *
 * Results are ranked strongest-first by the server. Field names match the
 * backend RepositoryActivityResult schema exactly.
 */
export interface RepositoryActivityResult {
  provider_project_id: string
  name: string
  path_with_namespace: string
  contributing_member_count: number
  merge_request_count: number
  last_activity_at: string
}

/** Fetch the team's currently saved GitLab repositories. */
export async function listGitLabRepositories(teamId: string): Promise<TeamGitLabRepository[]> {
  return apiFetch<TeamGitLabRepository[]>(`/teams/${teamId}/gitlab/repositories`)
}

/**
 * Replace the team's GitLab repository list with the supplied set (replace
 * semantics — the server validates each id and returns the saved rows).
 */
export async function replaceGitLabRepositories(
  teamId: string,
  repositories: GitLabRepositoryInput[],
): Promise<TeamGitLabRepository[]> {
  return apiFetch<TeamGitLabRepository[]>(`/teams/${teamId}/gitlab/repositories`, {
    method: "PUT",
    body: JSON.stringify(repositories),
  })
}

/**
 * Server-side search for GitLab projects matching `q`.
 *
 * Results are paginated by the server; the caller is responsible for debouncing
 * before invoking this function (§24).
 */
export async function searchGitLabProjects(
  teamId: string,
  q: string,
  limit?: number,
  page?: number,
): Promise<ProjectSearchResult[]> {
  const params = new URLSearchParams({ q })
  if (limit !== undefined) params.set("limit", String(limit))
  if (page !== undefined) params.set("page", String(page))
  return apiFetch<ProjectSearchResult[]>(
    `/teams/${teamId}/gitlab/project-search?${params.toString()}`,
  )
}

/**
 * Fetch ranked repository suggestions derived from the team's selected members'
 * recent activity (§10, §11). Empty when no members are saved yet.
 */
export async function getRepositorySuggestions(
  teamId: string,
  limit?: number,
): Promise<RepositoryActivityResult[]> {
  const params = new URLSearchParams()
  if (limit !== undefined) params.set("limit", String(limit))
  const qs = params.toString()
  return apiFetch<RepositoryActivityResult[]>(
    `/teams/${teamId}/gitlab/repository-suggestions${qs ? `?${qs}` : ""}`,
  )
}
