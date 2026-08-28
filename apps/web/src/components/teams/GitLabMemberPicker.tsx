// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { Combobox, type ComboboxOption } from "@/components/ui/combobox"
import { apiErrorMessage } from "@/lib/api"
import {
  listGitLabMembers,
  replaceGitLabMembers,
  searchGitLabMembers,
  type GitLabMemberSearchResult,
  type TeamGitLabMember,
} from "@/lib/gitlabScope"

/** In-memory representation of a selected member — normalises the two
 *  source shapes (search result vs. saved member) into one. */
interface LocalMember {
  gitlab_user_id: number
  username: string
  display_name: string | null
}

/** Arguments for the replace mutation — carries both the new set and a
 *  pre-mutation snapshot so onError can roll back without stale-closure risk. */
interface PersistArgs {
  members: LocalMember[]
  snapshot: LocalMember[]
}

export interface GitLabMemberPickerProps {
  teamId: string
  /** The team's active GitLab code connection id. Only members anchored to it are shown/saved. */
  connectionId: string
}

function memberLabel(m: { username: string; display_name: string | null }): string {
  return m.display_name ? `${m.display_name} @${m.username}` : `@${m.username}`
}

function savedMemberToLocal(m: TeamGitLabMember): LocalMember {
  return {
    gitlab_user_id: m.gitlab_user_id,
    username: m.username,
    display_name: m.display_name,
  }
}

/**
 * Searchable, selection-only GitLab member autocomplete backed by the
 * server-side member-search endpoint (§5.1, §5.2, §24).
 *
 * - Debounces the query ~300 ms before fetching from the server.
 * - Only a real search result can be added; blurring free text adds nothing.
 * - Selected members are displayed as removable rows.
 * - Selections and removals are immediately persisted via PUT (replace
 *   semantics). The UI is reconciled from the authoritative PUT response.
 * - The picker is gated on the initial members load: no interaction is
 *   possible until the GET succeeds, preventing a destructive replace from
 *   an empty baseline.
 */
export function GitLabMemberPicker({ teamId, connectionId }: GitLabMemberPickerProps) {
  const queryClient = useQueryClient()

  // Raw query updated on every keystroke; debouncedQuery drives the search fetch.
  const [rawQuery, setRawQuery] = useState("")
  const [debouncedQuery, setDebouncedQuery] = useState("")

  // The authoritative selection displayed as chips. Seeded from the server
  // on first successful load; reconciled from the PUT response on each save.
  const [selectedMembers, setSelectedMembers] = useState<LocalMember[]>([])
  const [initialized, setInitialized] = useState(false)

  // Key prop used to force-remount the Combobox after each selection so it
  // resets to an empty, closed state without external control of its internals.
  const [comboboxKey, setComboboxKey] = useState(0)

  // Surfaces mutation errors (add/remove failures) inline below the picker.
  const [mutationError, setMutationError] = useState<string | null>(null)

  // Debounce: replace debouncedQuery with rawQuery after 300 ms of inactivity.
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(rawQuery), 300)
    return () => clearTimeout(timer)
  }, [rawQuery])

  // Load saved members on mount; the query status gates the entire picker.
  const {
    data: savedMembers,
    isLoading: membersLoading,
    isError: membersIsError,
    error: membersError,
  } = useQuery({
    queryKey: ["gitlab-members", teamId],
    queryFn: () => listGitLabMembers(teamId),
  })

  // Seed selectedMembers from the server exactly once (first successful load).
  // Only members anchored to the active connection are seeded: rows left over from a
  // previous connection must not be shown or re-sent (their numeric ids are instance-local
  // and would resolve to unrelated accounts on the current instance).
  useEffect(() => {
    if (savedMembers !== undefined && !initialized) {
      setSelectedMembers(
        savedMembers
          .filter((m) => m.connection_id === connectionId)
          .map(savedMemberToLocal),
      )
      setInitialized(true)
    }
  }, [savedMembers, initialized, connectionId])

  // Server-side search — enabled only when a non-empty debounced query exists.
  const { data: searchResults = [] } = useQuery<GitLabMemberSearchResult[]>({
    queryKey: ["gitlab-member-search", teamId, debouncedQuery],
    queryFn: () => searchGitLabMembers(teamId, debouncedQuery),
    enabled: debouncedQuery.trim().length > 0,
  })

  // PUT the full member set on each change (replace semantics).
  // The snapshot in variables lets onError roll back without stale-closure risk.
  const { mutate: persistMembers, isPending: isSaving } = useMutation<
    TeamGitLabMember[],
    Error,
    PersistArgs
  >({
    mutationFn: ({ members }) =>
      replaceGitLabMembers(
        teamId,
        members.map((m) => ({ gitlab_user_id: m.gitlab_user_id })),
      ),
    onSuccess: (data) => {
      // Reconcile from the authoritative response so server normalisation and
      // deduplication are reflected in the UI without a redundant round-trip.
      setSelectedMembers(data.map(savedMemberToLocal))
      setMutationError(null)
      // Keep the query cache in sync for future mounts of this picker.
      queryClient.setQueryData(["gitlab-members", teamId], data)
    },
    onError: (err, { snapshot }) => {
      // Roll back the optimistic update to the pre-mutation state so a failed
      // write never looks successful.
      setSelectedMembers(snapshot)
      setMutationError(apiErrorMessage(err, "Failed to save members. Please try again."))
    },
  })

  // Build combobox options from search results, excluding already-selected members.
  const selectedIds = new Set(selectedMembers.map((m) => String(m.gitlab_user_id)))
  const options: ComboboxOption[] = searchResults
    .filter((r) => !selectedIds.has(r.provider_user_id))
    .map((r) => ({
      value: r.provider_user_id,
      label: memberLabel({ username: r.username, display_name: r.display_name || null }),
      // Map avatar_url into the Combobox option model (§5.1 avatar if available).
      imageUrl: r.avatar_url ?? undefined,
    }))

  function handleSelect(value: string) {
    // Serialize writes: ignore edits while a replace PUT is in flight so an older,
    // larger full-set request cannot commit after a newer one and resurrect members.
    if (isSaving) return
    // Only real search results can be selected (§5.2); the Combobox's onSelect
    // fires exclusively for actual options so no free-text guard is needed here,
    // but we double-check that the value maps to a known result.
    const result = searchResults.find((r) => r.provider_user_id === value)
    if (!result) return

    const gitlabUserId = parseInt(value, 10)
    if (isNaN(gitlabUserId)) return
    if (selectedIds.has(String(gitlabUserId))) return

    const newMember: LocalMember = {
      gitlab_user_id: gitlabUserId,
      username: result.username,
      display_name: result.display_name || null,
    }
    // Capture the snapshot before the optimistic update so onError can roll back.
    const snapshot = [...selectedMembers]
    const newMembers = [...selectedMembers, newMember]
    setSelectedMembers(newMembers)
    persistMembers({ members: newMembers, snapshot })

    // Reset the search state and remount the Combobox with a fresh key so the
    // input clears and the listbox closes without exposing internal state.
    setRawQuery("")
    setDebouncedQuery("")
    setComboboxKey((k) => k + 1)
  }

  function handleRemove(gitlabUserId: number) {
    if (isSaving) return
    const snapshot = [...selectedMembers]
    const newMembers = selectedMembers.filter((m) => m.gitlab_user_id !== gitlabUserId)
    setSelectedMembers(newMembers)
    persistMembers({ members: newMembers, snapshot })
  }

  // Gate the picker: a failed or pending initial load must not enable a
  // destructive replace from an unknown (or empty) baseline.
  if (membersLoading) {
    return <p className="text-sm text-slate-500">Loading members...</p>
  }

  if (membersIsError) {
    return (
      <p className="text-sm text-destructive" role="alert">
        {apiErrorMessage(membersError, "Failed to load members.")}
      </p>
    )
  }

  return (
    <div className="space-y-2">
      <Combobox
        key={comboboxKey}
        disabled={isSaving}
        inputLabel="Search GitLab members"
        onQueryChange={setRawQuery}
        onSelect={handleSelect}
        options={options}
        placeholder="Search by name or username..."
      />
      {mutationError && (
        <p className="mt-1 text-sm text-destructive" role="alert">
          {mutationError}
        </p>
      )}
      {selectedMembers.length > 0 && (
        <ul aria-label="Selected GitLab members" className="space-y-1">
          {selectedMembers.map((m) => (
            <li
              key={m.gitlab_user_id}
              className="flex items-center justify-between rounded-md border px-3 py-1.5 text-sm"
            >
              <span>{memberLabel(m)}</span>
              <button
                aria-label={`Remove ${m.display_name ?? m.username}`}
                className="ml-2 text-slate-400 hover:text-slate-700 disabled:opacity-50"
                disabled={isSaving}
                onClick={() => handleRemove(m.gitlab_user_id)}
                type="button"
              >
                &times;
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
