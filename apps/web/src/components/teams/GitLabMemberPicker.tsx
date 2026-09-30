// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { BulkMemberPaste, type ResolvedMember } from "@/components/teams/BulkMemberPaste"
import { Combobox, type ComboboxOption } from "@/components/ui/combobox"
import { apiErrorMessage } from "@/lib/api"
import {
  listGitLabGroupMembers,
  listGitLabMembers,
  replaceGitLabMembers,
  searchGitLabGroups,
  searchGitLabMembers,
  type GitLabMemberSearchResult,
  type GroupRef,
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
  // Tracks which connectionId was last used to seed selectedMembers so the effect
  // re-seeds whenever the active connection changes while the component stays mounted.
  const [seededConnectionId, setSeededConnectionId] = useState<string | null>(null)

  // Key prop used to force-remount the Combobox after each selection so it
  // resets to an empty, closed state without external control of its internals.
  const [comboboxKey, setComboboxKey] = useState(0)

  // Surfaces mutation errors (add/remove failures) inline below the picker.
  const [mutationError, setMutationError] = useState<string | null>(null)

  // Controls visibility of the bulk paste panel.
  const [showPastePanel, setShowPastePanel] = useState(false)

  // Controls visibility of the group import panel.
  const [showGroupPanel, setShowGroupPanel] = useState(false)
  // Group search debounce state.
  const [rawGroupQuery, setRawGroupQuery] = useState("")
  const [debouncedGroupQuery, setDebouncedGroupQuery] = useState("")
  // The group selected by the user in the group combobox.
  const [selectedGroup, setSelectedGroup] = useState<GroupRef | null>(null)
  // Key to remount the group combobox after selection so it resets cleanly.
  const [groupComboboxKey, setGroupComboboxKey] = useState(0)
  // Set of provider_user_id values the user has checked as candidates to add.
  const [checkedCandidates, setCheckedCandidates] = useState<Set<string>>(new Set())

  // Debounce: replace debouncedQuery with rawQuery after 300 ms of inactivity.
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(rawQuery), 300)
    return () => clearTimeout(timer)
  }, [rawQuery])

  // Debounce group query with the same window as the member search.
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedGroupQuery(rawGroupQuery), 300)
    return () => clearTimeout(timer)
  }, [rawGroupQuery])

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

  // Seed selectedMembers whenever the active connection changes (or on first load).
  // Comparing seededConnectionId to connectionId detects a mid-mount connection switch
  // so selectedMembers is never left showing the previous connection's user ids
  // (numeric ids are instance-local and would resolve to unrelated accounts on another instance).
  useEffect(() => {
    if (savedMembers !== undefined && seededConnectionId !== connectionId) {
      setSelectedMembers(
        savedMembers
          .filter((m) => m.connection_id === connectionId)
          .map(savedMemberToLocal),
      )
      setSeededConnectionId(connectionId)
    }
  }, [savedMembers, connectionId, seededConnectionId])

  // Server-side search — enabled only when a non-empty debounced query exists.
  // connectionId is included in the key so search results are scoped per connection.
  const { data: searchResults = [] } = useQuery<GitLabMemberSearchResult[]>({
    queryKey: ["gitlab-member-search", teamId, connectionId, debouncedQuery],
    queryFn: () => searchGitLabMembers(teamId, debouncedQuery),
    enabled: debouncedQuery.trim().length > 0,
  })

  // Group search — enabled when the debounced group query is non-empty.
  const { data: groupSearchResults = [] } = useQuery<GroupRef[]>({
    queryKey: ["gitlab-group-search", teamId, connectionId, debouncedGroupQuery],
    queryFn: () => searchGitLabGroups(teamId, debouncedGroupQuery),
    enabled: debouncedGroupQuery.trim().length > 0,
  })

  // Group members — enabled once a group has been selected.
  const { data: groupMembers = [], isLoading: groupMembersLoading } =
    useQuery<GitLabMemberSearchResult[]>({
      queryKey: [
        "gitlab-group-members",
        teamId,
        connectionId,
        selectedGroup?.provider_group_id,
      ],
      queryFn: () => listGitLabGroupMembers(teamId, selectedGroup!.provider_group_id),
      enabled: selectedGroup !== null,
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
      // A membership change affects which repositories the server will suggest;
      // invalidate so the repository picker refetches suggestions on next mount
      // or immediately if it is currently mounted.
      queryClient.invalidateQueries({ queryKey: ["gitlab-repository-suggestions", teamId] })
    },
    onError: (err, { snapshot }) => {
      // Roll back the optimistic update to the pre-mutation state so a failed
      // write never looks successful.
      setSelectedMembers(snapshot)
      setMutationError(apiErrorMessage(err, "Failed to save members. Please try again."))
      // Even a failed write may have partially changed server state; invalidate
      // so stale suggestions are not shown indefinitely.
      queryClient.invalidateQueries({ queryKey: ["gitlab-repository-suggestions", teamId] })
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

  // Build group combobox options from group search results.
  const groupOptions: ComboboxOption[] = groupSearchResults.map((g) => ({
    value: g.provider_group_id,
    label: `${g.name} (${g.full_path})`,
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

  function handleBulkAdd(newMembers: ResolvedMember[]) {
    if (isSaving || newMembers.length === 0) return
    const existingIds = new Set(selectedMembers.map((m) => m.gitlab_user_id))
    const fresh = newMembers.filter((m) => !existingIds.has(m.gitlab_user_id))
    if (fresh.length === 0) return
    const snapshot = [...selectedMembers]
    const merged = [...selectedMembers, ...fresh]
    setSelectedMembers(merged)
    persistMembers({ members: merged, snapshot })
    setShowPastePanel(false)
  }

  function handleGroupSelect(value: string) {
    const group = groupSearchResults.find((g) => g.provider_group_id === value)
    if (!group) return
    setSelectedGroup(group)
    setCheckedCandidates(new Set())
    setRawGroupQuery("")
    setDebouncedGroupQuery("")
    setGroupComboboxKey((k) => k + 1)
  }

  function toggleCandidate(providerUserId: string) {
    setCheckedCandidates((prev) => {
      const next = new Set(prev)
      if (next.has(providerUserId)) {
        next.delete(providerUserId)
      } else {
        next.add(providerUserId)
      }
      return next
    })
  }

  function handleAddGroupMembers() {
    if (isSaving) return
    const existingIds = new Set(selectedMembers.map((m) => m.gitlab_user_id))
    const toAdd: LocalMember[] = []
    for (const m of groupMembers) {
      if (!checkedCandidates.has(m.provider_user_id)) continue
      const id = parseInt(m.provider_user_id, 10)
      if (isNaN(id) || existingIds.has(id)) continue
      toAdd.push({
        gitlab_user_id: id,
        username: m.username,
        display_name: m.display_name || null,
      })
    }
    if (toAdd.length === 0) {
      setShowGroupPanel(false)
      return
    }
    const snapshot = [...selectedMembers]
    const merged = [...selectedMembers, ...toAdd]
    setSelectedMembers(merged)
    persistMembers({ members: merged, snapshot })
    setShowGroupPanel(false)
    setSelectedGroup(null)
    setCheckedCandidates(new Set())
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
      <div className="flex items-center gap-2">
        <div className="flex-1">
          <Combobox
            key={comboboxKey}
            disabled={isSaving}
            inputLabel="Search GitLab members"
            onQueryChange={setRawQuery}
            onSelect={handleSelect}
            options={options}
            placeholder="Search by name or username..."
          />
        </div>
        <button
          aria-expanded={showPastePanel}
          aria-label="Paste a list"
          className="shrink-0 rounded-md border px-3 py-1.5 text-sm font-medium disabled:opacity-50"
          disabled={isSaving}
          onClick={() => setShowPastePanel((v) => !v)}
          type="button"
        >
          Paste a list
        </button>
        <button
          aria-expanded={showGroupPanel}
          aria-label="Import candidates from GitLab group"
          className="shrink-0 rounded-md border px-3 py-1.5 text-sm font-medium disabled:opacity-50"
          disabled={isSaving}
          onClick={() => {
            setShowGroupPanel((v) => !v)
            if (showGroupPanel) {
              setSelectedGroup(null)
              setCheckedCandidates(new Set())
            }
          }}
          type="button"
        >
          Import from group
        </button>
      </div>
      {showPastePanel && (
        <div className="rounded-md border p-3">
          <p className="mb-2 text-sm font-medium">Paste a list of names or usernames</p>
          <BulkMemberPaste
            disabled={isSaving}
            onAdd={handleBulkAdd}
            teamId={teamId}
          />
        </div>
      )}
      {showGroupPanel && (
        <div className="rounded-md border p-3">
          <p className="mb-2 text-sm font-medium">Import candidates from GitLab group</p>
          <Combobox
            key={groupComboboxKey}
            disabled={isSaving}
            inputLabel="Search GitLab groups"
            onQueryChange={setRawGroupQuery}
            onSelect={handleGroupSelect}
            options={groupOptions}
            placeholder="Search by group name..."
          />
          {selectedGroup !== null && (
            <div className="mt-3">
              <p className="mb-2 text-sm text-slate-600">
                Members of {selectedGroup.name} — select to add
              </p>
              {groupMembersLoading ? (
                <p className="text-sm text-slate-500">Loading group members...</p>
              ) : groupMembers.length === 0 ? (
                <p className="text-sm text-slate-500">No members found in this group.</p>
              ) : (
                <ul aria-label="Group member candidates" className="space-y-1">
                  {groupMembers.map((m) => {
                    const alreadyAdded = selectedIds.has(m.provider_user_id)
                    const isChecked = checkedCandidates.has(m.provider_user_id)
                    return (
                      <li
                        key={m.provider_user_id}
                        className="flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm"
                      >
                        <input
                          aria-label={`Select ${m.display_name ?? m.username}`}
                          checked={isChecked || alreadyAdded}
                          disabled={alreadyAdded || isSaving}
                          id={`group-candidate-${m.provider_user_id}`}
                          onChange={() => toggleCandidate(m.provider_user_id)}
                          type="checkbox"
                        />
                        <label htmlFor={`group-candidate-${m.provider_user_id}`}>
                          {memberLabel({
                            username: m.username,
                            display_name: m.display_name || null,
                          })}
                          {alreadyAdded && (
                            <span className="ml-1 text-xs text-slate-400">already added</span>
                          )}
                        </label>
                      </li>
                    )
                  })}
                </ul>
              )}
              {groupMembers.length > 0 && (
                <button
                  className="mt-2 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground disabled:opacity-50"
                  disabled={checkedCandidates.size === 0 || isSaving}
                  onClick={handleAddGroupMembers}
                  type="button"
                >
                  Add selected ({checkedCandidates.size})
                </button>
              )}
            </div>
          )}
        </div>
      )}
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
