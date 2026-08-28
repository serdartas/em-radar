// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { Combobox, type ComboboxOption } from "@/components/ui/combobox"
import { apiErrorMessage } from "@/lib/api"
import {
  getRepositorySuggestions,
  listGitLabRepositories,
  replaceGitLabRepositories,
  searchGitLabProjects,
  type RepositoryActivityResult,
  type TeamGitLabRepository,
} from "@/lib/gitlabScope"

/**
 * Minimum contributing-member count for a suggestion to be classified as a
 * "likely" team repository vs a lower-confidence one (§11).
 * Repositories with >= LIKELY_THRESHOLD contributors appear in the top group;
 * those below appear separately so stronger candidates are always shown first.
 */
const LIKELY_THRESHOLD = 2

/** In-memory representation of a confirmed repository — normalises the two
 *  source shapes (search result vs. saved repository) into one. */
interface LocalRepo {
  gitlab_project_id: number
  name: string
  path_with_namespace: string
}

/** Arguments for the replace mutation — carries both the new set and a
 *  pre-mutation snapshot so onError can roll back without stale-closure risk. */
interface PersistArgs {
  repos: LocalRepo[]
  snapshot: LocalRepo[]
}

export interface GitLabRepositoryPickerProps {
  teamId: string
  /** The team's active GitLab code connection id. Only repos anchored to it are shown/saved. */
  connectionId: string
}

function savedRepoToLocal(r: TeamGitLabRepository): LocalRepo {
  return {
    gitlab_project_id: r.gitlab_project_id,
    name: r.name,
    path_with_namespace: r.path_with_namespace,
  }
}

/** Format a UTC ISO timestamp as a human-readable relative string. */
function formatRelativeDate(isoString: string): string {
  const diffMs = Date.now() - new Date(isoString).getTime()
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))
  if (diffDays <= 0) return "today"
  if (diffDays === 1) return "yesterday"
  if (diffDays < 30) return `${diffDays}d ago`
  const diffMonths = Math.floor(diffDays / 30)
  if (diffMonths < 12) return `${diffMonths}mo ago`
  return `${Math.floor(diffMonths / 12)}y ago`
}

/** A single suggestion row with an explicit checkbox for confirmation (§12). */
function SuggestionRow({
  disabled,
  onConfirm,
  suggestion,
}: {
  suggestion: RepositoryActivityResult
  onConfirm: (s: RepositoryActivityResult) => void
  disabled: boolean
}) {
  const memberWord = suggestion.contributing_member_count === 1 ? "member" : "members"
  const activity = `${suggestion.contributing_member_count} ${memberWord} · ${suggestion.merge_request_count} MRs · ${formatRelativeDate(suggestion.last_activity_at)}`
  const inputId = `suggestion-${suggestion.provider_project_id}`

  return (
    <li className="flex items-start gap-3 rounded-md border px-3 py-2 text-sm">
      <input
        aria-label={`Confirm ${suggestion.path_with_namespace}`}
        className="mt-0.5 h-4 w-4 cursor-pointer"
        disabled={disabled}
        id={inputId}
        onChange={() => onConfirm(suggestion)}
        type="checkbox"
      />
      <label className="flex-1 cursor-pointer space-y-0.5" htmlFor={inputId}>
        <span className="font-medium">{suggestion.name}</span>
        <span className="block text-xs text-slate-500">{suggestion.path_with_namespace}</span>
        <span className="block text-xs text-slate-400">{activity}</span>
      </label>
    </li>
  )
}

/**
 * Ranked "Suggested repositories" picker backed by the M9-05 endpoints (§9-§14, §24).
 *
 * Safety patterns (mirror GitLabMemberPicker):
 * - LOAD GATE: gates all interaction on the initial repositories GET succeeding.
 * - CONNECTION-SCOPED SEED: only repos whose connection_id matches the active
 *   connectionId are seeded; stale-connection rows are never shown or re-sent.
 * - onError ROLLBACK: snapshots the selection before each optimistic update;
 *   rolls back on mutation failure.
 * - RECONCILE: updates local state from the authoritative PUT response so server
 *   normalisation is reflected without a redundant round-trip.
 * - SERIALIZE WRITES: the Combobox, suggestion checkboxes, and remove buttons are
 *   disabled while a replace PUT is in flight, preventing overlapping full-set PUTs.
 */
export function GitLabRepositoryPicker({ connectionId, teamId }: GitLabRepositoryPickerProps) {
  const queryClient = useQueryClient()

  // Raw query updated on every keystroke; debouncedQuery drives the search fetch.
  const [rawQuery, setRawQuery] = useState("")
  const [debouncedQuery, setDebouncedQuery] = useState("")

  // The authoritative confirmed set displayed as chips. Seeded from the server
  // on first successful load; reconciled from the PUT response on each save.
  const [selectedRepos, setSelectedRepos] = useState<LocalRepo[]>([])
  // Tracks which connectionId was last used to seed selectedRepos so the effect
  // re-seeds whenever the active connection changes while the component stays mounted.
  const [seededConnectionId, setSeededConnectionId] = useState<string | null>(null)

  // Key prop used to force-remount the Combobox after each selection so it
  // resets to an empty, closed state without exposing its internals.
  const [comboboxKey, setComboboxKey] = useState(0)

  // Surfaces mutation errors (add/remove failures) inline below the picker.
  const [mutationError, setMutationError] = useState<string | null>(null)

  // Debounce: replace debouncedQuery with rawQuery after 300 ms of inactivity.
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(rawQuery), 300)
    return () => clearTimeout(timer)
  }, [rawQuery])

  // Load saved repositories on mount; the query status gates the entire picker.
  const {
    data: savedRepos,
    error: reposError,
    isError: reposIsError,
    isLoading: reposLoading,
  } = useQuery({
    queryKey: ["gitlab-repositories", teamId],
    queryFn: () => listGitLabRepositories(teamId),
  })

  // Seed selectedRepos whenever the active connection changes (or on first load).
  // Comparing seededConnectionId to connectionId detects a mid-mount connection switch
  // so selectedRepos is never left showing the previous connection's project ids
  // (numeric ids are instance-local and would resolve to wrong projects on another instance).
  useEffect(() => {
    if (savedRepos !== undefined && seededConnectionId !== connectionId) {
      setSelectedRepos(
        savedRepos.filter((r) => r.connection_id === connectionId).map(savedRepoToLocal),
      )
      setSeededConnectionId(connectionId)
    }
  }, [savedRepos, connectionId, seededConnectionId])

  // Load ranked suggestions from members' recent activity (§10, §11).
  // connectionId is included in the key so suggestions refetch per connection rather
  // than sharing a cross-connection cache entry.
  const {
    data: suggestions = [],
    isError: suggestionsIsError,
    error: suggestionsError,
  } = useQuery<RepositoryActivityResult[]>({
    queryKey: ["gitlab-repository-suggestions", teamId, connectionId],
    queryFn: () => getRepositorySuggestions(teamId),
  })

  // Server-side project search — enabled only when a non-empty debounced query exists.
  // connectionId is included in the key so search results are scoped per connection.
  const { data: searchResults = [] } = useQuery({
    queryKey: ["gitlab-project-search", teamId, connectionId, debouncedQuery],
    queryFn: () => searchGitLabProjects(teamId, debouncedQuery),
    enabled: debouncedQuery.trim().length > 0,
  })

  // PUT the full repository set on each change (replace semantics).
  const { isPending: isSaving, mutate: persistRepos } = useMutation<
    TeamGitLabRepository[],
    Error,
    PersistArgs
  >({
    mutationFn: ({ repos }) =>
      replaceGitLabRepositories(
        teamId,
        repos.map((r) => ({ gitlab_project_id: r.gitlab_project_id })),
      ),
    onError: (err, { snapshot }) => {
      // Roll back the optimistic update so a failed write never looks successful.
      setSelectedRepos(snapshot)
      setMutationError(
        apiErrorMessage(err, "Failed to save repositories. Please try again."),
      )
    },
    onSuccess: (data) => {
      // Reconcile from the authoritative response so server normalisation and
      // deduplication are reflected in the UI without a redundant round-trip.
      setSelectedRepos(data.map(savedRepoToLocal))
      setMutationError(null)
      // Keep the query cache in sync for future mounts of this picker.
      queryClient.setQueryData(["gitlab-repositories", teamId], data)
    },
  })

  // Gate the picker: a failed or pending initial load must not enable a
  // destructive replace from an unknown (or empty) baseline.
  if (reposLoading) {
    return <p className="text-sm text-slate-500">Loading repositories...</p>
  }

  if (reposIsError) {
    return (
      <p className="text-sm text-destructive" role="alert">
        {apiErrorMessage(reposError, "Failed to load repositories.")}
      </p>
    )
  }

  const selectedIds = new Set(selectedRepos.map((r) => String(r.gitlab_project_id)))

  // Exclude already-confirmed repos from suggestions so they do not appear as checkboxes.
  const unconfirmedSuggestions = suggestions.filter(
    (s) => !selectedIds.has(s.provider_project_id),
  )
  const likelySuggestions = unconfirmedSuggestions.filter(
    (s) => s.contributing_member_count >= LIKELY_THRESHOLD,
  )
  const lowerConfidenceSuggestions = unconfirmedSuggestions.filter(
    (s) => s.contributing_member_count < LIKELY_THRESHOLD,
  )

  // Build search options, excluding already-confirmed repos (§13).
  const searchOptions: ComboboxOption[] = searchResults
    .filter((r) => !selectedIds.has(r.provider_project_id))
    .map((r) => ({ label: r.path_with_namespace, value: r.provider_project_id }))

  // Optimistically append a repo and persist the full confirmed set (replace semantics),
  // snapshotting first so onError can roll back.
  function addRepo(repo: LocalRepo) {
    const snapshot = [...selectedRepos]
    const newRepos = [...selectedRepos, repo]
    setSelectedRepos(newRepos)
    persistRepos({ repos: newRepos, snapshot })
  }

  function handleConfirmSuggestion(suggestion: RepositoryActivityResult) {
    // Serialize writes: ignore edits while a replace PUT is in flight.
    if (isSaving) return
    const projectId = parseInt(suggestion.provider_project_id, 10)
    if (isNaN(projectId) || selectedIds.has(suggestion.provider_project_id)) return
    addRepo({
      gitlab_project_id: projectId,
      name: suggestion.name,
      path_with_namespace: suggestion.path_with_namespace,
    })
  }

  function handleSelectFromSearch(value: string) {
    // Serialize writes: ignore edits while a replace PUT is in flight.
    if (isSaving) return
    // Only real search results can be selected (§13); the Combobox's onSelect
    // fires exclusively for actual options, but we double-check the value maps
    // to a known result to guard against unexpected calls.
    const result = searchResults.find((r) => r.provider_project_id === value)
    if (!result) return
    const projectId = parseInt(value, 10)
    if (isNaN(projectId) || selectedIds.has(value)) return
    addRepo({
      gitlab_project_id: projectId,
      name: result.name,
      path_with_namespace: result.path_with_namespace,
    })
    // Reset the search state and remount the Combobox with a fresh key.
    setRawQuery("")
    setDebouncedQuery("")
    setComboboxKey((k) => k + 1)
  }

  function handleRemove(projectId: number) {
    if (isSaving) return
    const snapshot = [...selectedRepos]
    const newRepos = selectedRepos.filter((r) => r.gitlab_project_id !== projectId)
    setSelectedRepos(newRepos)
    persistRepos({ repos: newRepos, snapshot })
  }

  return (
    <div className="space-y-4">
      {/* Confirmed repositories — shown as removable chips (§14). */}
      {selectedRepos.length > 0 && (
        <ul aria-label="Confirmed repositories" className="space-y-1">
          {selectedRepos.map((r) => (
            <li
              key={r.gitlab_project_id}
              className="flex items-center justify-between rounded-md border px-3 py-1.5 text-sm"
            >
              <span>
                <span className="font-medium">{r.name}</span>
                <span className="ml-1 text-slate-500">{r.path_with_namespace}</span>
              </span>
              <button
                aria-label={`Remove ${r.name}`}
                className="ml-2 text-slate-400 hover:text-slate-700 disabled:opacity-50"
                disabled={isSaving}
                onClick={() => handleRemove(r.gitlab_project_id)}
                type="button"
              >
                &times;
              </button>
            </li>
          ))}
        </ul>
      )}

      {/* Suggested repositories — ranked from member activity (§10, §11, §12).
          Heading deliberately says "Suggested repositories" not "Team repositories"
          because contribution does not imply ownership (§10). */}
      <div>
        <h5 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Suggested repositories
        </h5>
        {suggestionsIsError ? (
          <p className="text-sm text-destructive" role="alert">
            {apiErrorMessage(suggestionsError, "Failed to load repository suggestions.")}
          </p>
        ) : suggestions.length === 0 ? (
          <p className="text-sm text-slate-400">
            No suggestions yet - add members to generate repository suggestions.
          </p>
        ) : (
          unconfirmedSuggestions.length === 0 && (
            <p className="text-sm text-slate-400">All suggestions confirmed.</p>
          )
        )}
        {likelySuggestions.length > 0 && (
          <ul aria-label="Likely repositories" className="space-y-1.5">
            {likelySuggestions.map((s) => (
              <SuggestionRow
                key={s.provider_project_id}
                disabled={isSaving}
                onConfirm={handleConfirmSuggestion}
                suggestion={s}
              />
            ))}
          </ul>
        )}
        {lowerConfidenceSuggestions.length > 0 && (
          <div className="mt-2">
            <p className="mb-1 text-xs text-slate-400">Lower confidence</p>
            <ul aria-label="Lower-confidence repositories" className="space-y-1.5">
              {lowerConfidenceSuggestions.map((s) => (
                <SuggestionRow
                  key={s.provider_project_id}
                  disabled={isSaving}
                  onConfirm={handleConfirmSuggestion}
                  suggestion={s}
                />
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Add repository autocomplete backed by the project-search endpoint (§13, §24). */}
      <div>
        <p className="mb-1 text-xs font-medium text-slate-600">Add repository</p>
        <Combobox
          key={comboboxKey}
          disabled={isSaving}
          inputLabel="Search GitLab repositories"
          onQueryChange={setRawQuery}
          onSelect={handleSelectFromSearch}
          options={searchOptions}
          placeholder="Search by name or namespace..."
        />
      </div>

      {mutationError && (
        <p className="mt-1 text-sm text-destructive" role="alert">
          {mutationError}
        </p>
      )}
    </div>
  )
}
