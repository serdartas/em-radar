// SPDX-License-Identifier: Apache-2.0

import { useState } from "react"
import { useQuery } from "@tanstack/react-query"

import { apiErrorMessage } from "@/lib/api"
import {
  getMemberSuggestions,
  type ConfidenceBand,
  type GitLabMemberSearchResult,
  type MemberSuggestion,
} from "@/lib/gitlabScope"

/** A member ready to be added — matches the LocalMember shape in GitLabMemberPicker. */
export interface SuggestedMember {
  gitlab_user_id: number
  username: string
  display_name: string | null
}

export interface JiraActivitySuggestionsProps {
  teamId: string
  /** Provider user ids already in the team member list — excluded from the suggestions list. */
  selectedIds: Set<string>
  /** Whether a save (PUT) is in flight. Disables all interaction. */
  isSaving: boolean
  /** Called when the user confirms one or more suggestions to add. */
  onAdd: (members: SuggestedMember[]) => void
}

/** Map a GitLabMemberSearchResult to the SuggestedMember shape. */
function toSuggestedMember(ref: GitLabMemberSearchResult): SuggestedMember {
  return {
    gitlab_user_id: parseInt(ref.provider_user_id, 10),
    username: ref.username,
    display_name: ref.display_name || null,
  }
}

function confidenceLabel(band: ConfidenceBand): string {
  return band === "high" ? "High confidence" : "Uncertain"
}

/** Renders a single suggestion row with its confidence badge and action controls. */
function SuggestionRow({
  suggestion,
  confirmed,
  selectedCandidate,
  isSaving,
  alreadyAdded,
  onToggleConfirm,
  onSelectCandidate,
}: {
  suggestion: MemberSuggestion
  confirmed: boolean
  selectedCandidate: GitLabMemberSearchResult | null
  isSaving: boolean
  alreadyAdded: boolean
  onToggleConfirm: () => void
  onSelectCandidate: (ref: GitLabMemberSearchResult | null) => void
}) {
  const isHigh = suggestion.confidence === "high"
  const effectiveMatch = isHigh ? suggestion.match : selectedCandidate
  const canConfirm = !alreadyAdded && effectiveMatch !== null

  return (
    <li className="rounded-md border px-3 py-2 text-sm space-y-1">
      <div className="flex items-center gap-2">
        <span
          className={`shrink-0 text-xs font-semibold px-1.5 py-0.5 rounded ${
            isHigh
              ? "bg-green-100 text-green-800"
              : "bg-amber-100 text-amber-800"
          }`}
          aria-label={confidenceLabel(suggestion.confidence)}
        >
          {isHigh ? "✓" : "?"} {confidenceLabel(suggestion.confidence)}
        </span>
        <span className="font-medium">{suggestion.jira_person.display_name}</span>
        {suggestion.jira_person.email_address && (
          <span className="text-xs text-slate-400">
            ({suggestion.jira_person.email_address})
          </span>
        )}
      </div>

      {isHigh && suggestion.match !== null && (
        <p className="text-xs text-slate-600 pl-1">
          GitLab:{" "}
          <span className="font-medium">{suggestion.match.display_name}</span>{" "}
          <span className="text-slate-400">@{suggestion.match.username}</span>
        </p>
      )}

      {!isHigh && suggestion.candidates.length > 0 && (
        <div className="pl-1">
          <label className="text-xs text-slate-600 block mb-1">
            Select the matching GitLab user:
          </label>
          <select
            aria-label={`Select GitLab user for ${suggestion.jira_person.display_name}`}
            className="w-full rounded border px-2 py-1 text-xs disabled:opacity-50"
            disabled={isSaving || alreadyAdded}
            onChange={(e) => {
              const val = e.target.value
              const found = suggestion.candidates.find((c) => c.provider_user_id === val)
              onSelectCandidate(found ?? null)
            }}
            value={selectedCandidate?.provider_user_id ?? ""}
          >
            <option value="">-- choose --</option>
            {suggestion.candidates.map((c) => (
              <option key={c.provider_user_id} value={c.provider_user_id}>
                {c.display_name} @{c.username}
              </option>
            ))}
          </select>
        </div>
      )}

      {!isHigh && suggestion.candidates.length === 0 && (
        <p className="text-xs text-slate-400 pl-1">No GitLab users found for this name.</p>
      )}

      {alreadyAdded ? (
        <p className="text-xs text-slate-400 pl-1">Already a member.</p>
      ) : (
        <button
          aria-label={`${confirmed ? "Unconfirm" : "Confirm"} ${suggestion.jira_person.display_name}`}
          aria-pressed={confirmed}
          className={`mt-1 rounded px-2 py-0.5 text-xs font-medium disabled:opacity-50 ${
            confirmed
              ? "bg-primary text-primary-foreground"
              : "border text-slate-700 hover:bg-slate-50"
          }`}
          disabled={isSaving || !canConfirm}
          onClick={onToggleConfirm}
          type="button"
        >
          {confirmed ? "Confirmed" : "Confirm"}
        </button>
      )}
    </li>
  )
}

/** Stable identity key for a suggestion — Jira account_id when available, else display_name. */
function suggestionKey(s: MemberSuggestion): string {
  return s.jira_person.account_id ?? s.jira_person.display_name ?? ""
}

/**
 * Panel that fetches Jira-activity-based GitLab member suggestions and lets the
 * user confirm which ones to add. Only confirmed suggestions are passed to `onAdd`
 * — nothing is added automatically.
 *
 * High-confidence suggestions show a single match with a checkmark badge.
 * Uncertain suggestions require the user to select a candidate before confirming.
 */
export function JiraActivitySuggestions({
  teamId,
  selectedIds,
  isSaving,
  onAdd,
}: JiraActivitySuggestionsProps) {
  // Track confirmed state by stable Jira identity key (not array index) so a
  // background refetch that reorders or shrinks the list cannot cause a different
  // user to be added than the one the human confirmed.
  const [confirmed, setConfirmed] = useState<Set<string>>(new Set())
  // Track the user's candidate choice for uncertain suggestions (stable key → ref).
  const [candidateSelections, setCandidateSelections] = useState<
    Map<string, GitLabMemberSearchResult>
  >(new Map())

  const {
    data,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ["gitlab-member-suggestions", teamId],
    queryFn: () => getMemberSuggestions(teamId),
  })

  function toggleConfirm(key: string) {
    setConfirmed((prev) => {
      const next = new Set(prev)
      if (next.has(key)) {
        next.delete(key)
      } else {
        next.add(key)
      }
      return next
    })
  }

  function selectCandidate(key: string, ref: GitLabMemberSearchResult | null) {
    setCandidateSelections((prev) => {
      const next = new Map(prev)
      if (ref === null) {
        next.delete(key)
      } else {
        next.set(key, ref)
      }
      return next
    })
    // Deconfirm when the selection changes so the user must re-confirm.
    setConfirmed((prev) => {
      const next = new Set(prev)
      next.delete(key)
      return next
    })
  }

  function handleAddConfirmed() {
    if (isSaving || !data) return
    const toAdd: SuggestedMember[] = []
    for (const key of confirmed) {
      // Look up by stable identity — if the suggestion disappeared in a refetch, skip it.
      const s = data.suggestions.find((s) => suggestionKey(s) === key)
      if (s === undefined) continue
      const ref =
        s.confidence === "high" ? s.match : (candidateSelections.get(key) ?? null)
      if (ref === null) continue
      const id = parseInt(ref.provider_user_id, 10)
      if (isNaN(id) || selectedIds.has(ref.provider_user_id)) continue
      toAdd.push(toSuggestedMember(ref))
    }
    if (toAdd.length > 0) {
      onAdd(toAdd)
    }
    setConfirmed(new Set())
    setCandidateSelections(new Map())
  }

  if (isLoading) {
    return <p className="text-sm text-slate-500">Loading suggestions...</p>
  }

  if (isError) {
    return (
      <p className="text-sm text-destructive" role="alert">
        {apiErrorMessage(error, "Failed to load member suggestions.")}
      </p>
    )
  }

  if (!data || data.suggestions.length === 0) {
    return (
      <p className="text-sm text-slate-500">
        No suggestions found. The team may not have a Jira connection or no
        recently active Jira users could be matched to GitLab accounts.
      </p>
    )
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-slate-500">
        Based on Jira activity in the last {data.window_days} days. Confirm
        suggestions to add them as members.
      </p>
      <ul aria-label="Jira activity suggestions" className="space-y-2">
        {data.suggestions.map((s) => {
          const key = suggestionKey(s)
          const effectiveRef =
            s.confidence === "high" ? s.match : (candidateSelections.get(key) ?? null)
          const alreadyAdded =
            effectiveRef !== null && selectedIds.has(effectiveRef.provider_user_id)
          return (
            <SuggestionRow
              alreadyAdded={alreadyAdded}
              confirmed={confirmed.has(key)}
              isSaving={isSaving}
              key={key}
              onSelectCandidate={(ref) => selectCandidate(key, ref)}
              onToggleConfirm={() => toggleConfirm(key)}
              selectedCandidate={candidateSelections.get(key) ?? null}
              suggestion={s}
            />
          )
        })}
      </ul>
      {confirmed.size > 0 && (
        <button
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground disabled:opacity-50"
          disabled={isSaving}
          onClick={handleAddConfirmed}
          type="button"
        >
          Add confirmed ({confirmed.size})
        </button>
      )}
    </div>
  )
}
