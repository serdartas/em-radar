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
