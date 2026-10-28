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

// ---------------------------------------------------------------------------
// Bulk member resolve types and API function (M9-13)
// ---------------------------------------------------------------------------

/**
 * Classification returned per entry by the bulk-resolve endpoint.
 *
 * - matched: exactly one GitLab user matched the entry.
 * - ambiguous: more than one user matched; requires explicit selection.
 * - unmatched: no user matched; cannot be added.
 */
export type MemberResolveStatus = "matched" | "ambiguous" | "unmatched"

/**
 * Per-entry result from the bulk-resolve endpoint
 * (POST /api/teams/{teamId}/gitlab/member-resolve).
 */
export interface MemberResolveResult {
  entry: string
  status: MemberResolveStatus
  match: GitLabMemberSearchResult | null
  candidates: GitLabMemberSearchResult[]
}

/** Response envelope from the bulk-resolve endpoint. */
export interface BulkMemberResolveResponse {
  results: MemberResolveResult[]
}

/**
 * Resolve a list of raw name/username strings against GitLab.
 *
 * Each entry is classified by the server as matched, ambiguous, or unmatched.
 * Blank entries are skipped server-side. The caller is responsible for
 * splitting a pasted block into individual entries before calling this.
 */
export async function resolveGitLabMembers(
  teamId: string,
  entries: string[],
): Promise<BulkMemberResolveResponse> {
  return apiFetch<BulkMemberResolveResponse>(`/teams/${teamId}/gitlab/member-resolve`, {
    method: "POST",
    body: JSON.stringify({ entries }),
  })
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
// Group search and group member import (M9-14)
// ---------------------------------------------------------------------------

/**
 * A GitLab group result from the server-side group search endpoint
 * (GET /api/teams/{teamId}/gitlab/group-search).
 *
 * Field names match the backend GroupSearchResult schema exactly.
 */
export interface GroupRef {
  provider_group_id: string
  name: string
  full_path: string
}

/**
 * Search for GitLab groups matching `q`. Results are bounded server-side.
 * The caller is responsible for debouncing before invoking this function.
 */
export async function searchGitLabGroups(
  teamId: string,
  q: string,
  limit?: number,
  page?: number,
): Promise<GroupRef[]> {
  const params = new URLSearchParams({ q })
  if (limit !== undefined) params.set("limit", String(limit))
  if (page !== undefined) params.set("page", String(page))
  return apiFetch<GroupRef[]>(`/teams/${teamId}/gitlab/group-search?${params.toString()}`)
}

/**
 * List the members of a GitLab group by its provider group id or path.
 *
 * Returns MemberSearchResult-shaped items. Permission errors from the
 * connector surface as 502 on the server, not as empty lists.
 */
export async function listGitLabGroupMembers(
  teamId: string,
  groupId: string,
  limit?: number,
  page?: number,
): Promise<GitLabMemberSearchResult[]> {
  const params = new URLSearchParams({ group_id: groupId })
  if (limit !== undefined) params.set("limit", String(limit))
  if (page !== undefined) params.set("page", String(page))
  return apiFetch<GitLabMemberSearchResult[]>(
    `/teams/${teamId}/gitlab/group-members?${params.toString()}`,
  )
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

/**
 * Response envelope returned by the repository-suggestions endpoint.
 *
 * window_days reports the discovery window that was actually used (90 days by
 * default; 180 days when the default window returned too few candidates).
 * repositories is the ranked list of candidates for that window.
 */
export interface RepositorySuggestionsResponse {
  window_days: number
  repositories: RepositoryActivityResult[]
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
 * recent activity (§10, §11). Returns the response envelope including the
 * discovery window that was actually used and the ranked repository list.
 */
export async function getRepositorySuggestions(
  teamId: string,
  limit?: number,
): Promise<RepositorySuggestionsResponse> {
  const params = new URLSearchParams()
  if (limit !== undefined) params.set("limit", String(limit))
  const qs = params.toString()
  return apiFetch<RepositorySuggestionsResponse>(
    `/teams/${teamId}/gitlab/repository-suggestions${qs ? `?${qs}` : ""}`,
  )
}

// ---------------------------------------------------------------------------
// Member suggestions (M9-15: Jira activity with confidence scoring)
// ---------------------------------------------------------------------------

/**
 * A Jira user encountered as assignee or reporter on a recently updated issue.
 * Field names match the backend JiraPersonRef schema exactly.
 */
export interface JiraPersonRef {
  display_name: string
  email_address: string | null
  account_id: string | null
}

/**
 * Confidence band for a member suggestion.
 *
 * - high: exactly one GitLab user matched the Jira person's name.
 * - uncertain: zero or multiple candidates; requires explicit selection.
 */
export type ConfidenceBand = "high" | "uncertain"

/**
 * One suggestion: a Jira person with their best GitLab match candidates and a
 * confidence score. Field names match the backend MemberSuggestion schema exactly.
 */
export interface MemberSuggestion {
  jira_person: JiraPersonRef
  match: GitLabMemberSearchResult | null
  candidates: GitLabMemberSearchResult[]
  confidence: ConfidenceBand
}

/**
 * Response envelope from the member-suggestions endpoint
 * (GET /api/teams/{teamId}/gitlab/member-suggestions).
 */
export interface MemberSuggestionsResponse {
  window_days: number
  suggestions: MemberSuggestion[]
}

/**
 * Fetch member suggestions derived from Jira activity for the team. Returns a
 * list of Jira-active people with their best GitLab match candidates and
 * confidence scores. Returns an empty suggestion list when the team has no Jira
 * scope configured.
 */
export async function getMemberSuggestions(
  teamId: string,
): Promise<MemberSuggestionsResponse> {
  return apiFetch<MemberSuggestionsResponse>(
    `/teams/${teamId}/gitlab/member-suggestions`,
  )
}

// ---------------------------------------------------------------------------
// Config health verification (M9-16)
// ---------------------------------------------------------------------------

/**
 * Result of an on-demand configuration health verification.
 *
 * Contains all stored members and repositories with updated verification_status.
 * Rows with "unavailable" indicate deleted/archived entities; "unverified" indicates
 * a connector-instance mismatch (stored id may belong to a different GitLab instance).
 */
export interface ConfigHealthReport {
  members: TeamGitLabMember[]
  repositories: TeamGitLabRepository[]
}

/**
 * Trigger an on-demand health verification for a team's GitLab configuration.
 *
 * Re-resolves each stored member and repository against the GitLab connector by
 * stable id. Deleted users and archived repositories are marked unavailable;
 * renamed-but-same-id entities are refreshed; entries from a different connector
 * instance are marked unverified. Returns all rows with updated statuses.
 */
export async function verifyGitLabConfig(teamId: string): Promise<ConfigHealthReport> {
  return apiFetch<ConfigHealthReport>(`/teams/${teamId}/gitlab/verify-config`, {
    method: "POST",
  })
}

/**
 * Remove exactly one stored GitLab member row regardless of its verification status.
 * Designed for config-health cleanup: targets only the specified row without
 * touching other member entries.
 */
export async function deleteGitLabMember(teamId: string, memberId: string): Promise<void> {
  await apiFetch<void>(`/teams/${teamId}/gitlab/members/${memberId}`, { method: "DELETE" })
}

/**
 * Remove exactly one stored GitLab repository row regardless of its verification status.
 * Designed for config-health cleanup: targets only the specified row without
 * touching other repository entries.
 */
export async function deleteGitLabRepository(teamId: string, repoId: string): Promise<void> {
  await apiFetch<void>(`/teams/${teamId}/gitlab/repositories/${repoId}`, { method: "DELETE" })
}
