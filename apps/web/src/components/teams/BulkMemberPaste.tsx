// SPDX-License-Identifier: Apache-2.0

import { useState } from "react"

import { apiErrorMessage } from "@/lib/api"
import {
  resolveGitLabMembers,
  type GitLabMemberSearchResult,
  type MemberResolveResult,
} from "@/lib/gitlabScope"

export interface ResolvedMember {
  gitlab_user_id: number
  username: string
  display_name: string | null
}

export interface BulkMemberPasteProps {
  teamId: string
  /** When true, the "Add confirmed matches" button is disabled (e.g. a save is in flight). */
  disabled: boolean
  /**
   * Called when the user confirms the resolved set. Receives only confirmed matches:
   * entries with status "matched" plus ambiguous entries for which the user selected a candidate.
   * The parent is responsible for unioning with the current selection and persisting.
   */
  onAdd: (members: ResolvedMember[]) => void
}

function toResolved(r: GitLabMemberSearchResult): ResolvedMember | null {
  const id = parseInt(r.provider_user_id, 10)
  if (isNaN(id)) return null
  return { gitlab_user_id: id, username: r.username, display_name: r.display_name || null }
}

function parseEntries(raw: string): string[] {
  const seen = new Set<string>()
  const entries: string[] = []
  for (const part of raw.split(/[\n,]+/)) {
    const trimmed = part.trim()
    if (!trimmed) continue
    const key = trimmed.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    entries.push(trimmed)
  }
  return entries
}

/**
 * Paste-and-resolve panel for bulk GitLab member import.
 *
 * The user pastes a list of names or usernames (one per line or comma-separated),
 * clicks "Resolve", and each entry is classified by the server as:
 *   - matched (single result, auto-confirmed)
 *   - ambiguous (multiple results, requires explicit selection)
 *   - unmatched (no result, cannot be added)
 *
 * Only confirmed entries are forwarded via onAdd. Persistence (PUT) is handled by
 * the parent so the full replace-semantics set is built correctly.
 */
export function BulkMemberPaste({ teamId, disabled, onAdd }: BulkMemberPasteProps) {
  const [text, setText] = useState("")
  const [results, setResults] = useState<MemberResolveResult[] | null>(null)
  // User's selection for each ambiguous entry, keyed by result index (robust to duplicate
  // entry strings the backend may return).
  const [choices, setChoices] = useState<Record<number, GitLabMemberSearchResult>>({})
  const [isResolving, setIsResolving] = useState(false)
  const [resolveError, setResolveError] = useState<string | null>(null)

  async function handleResolve() {
    const entries = parseEntries(text)
    if (entries.length === 0) return
    setIsResolving(true)
    setResolveError(null)
    try {
      const response = await resolveGitLabMembers(teamId, entries)
      setResults(response.results)
      setChoices({})
    } catch (err) {
      setResolveError(apiErrorMessage(err as Error, "Failed to resolve entries. Please try again."))
      setResults(null)
    } finally {
      setIsResolving(false)
    }
  }

  function handleChoiceChange(
    index: number,
    providerUserId: string,
    candidates: GitLabMemberSearchResult[],
  ) {
    setChoices((prev) => {
      const next = { ...prev }
      const chosen = candidates.find((c) => c.provider_user_id === providerUserId)
      // Empty value ("Select a user...") clears a previous selection so it is no longer confirmed.
      if (chosen) {
        next[index] = chosen
      } else {
        delete next[index]
      }
      return next
    })
  }

  // The confirmed, persistable set: matched entries and ambiguous entries the user resolved,
  // each restricted to a result whose provider id maps to a member (so the count shown always
  // equals what is actually sent).
  function buildConfirmed(): ResolvedMember[] {
    if (!results) return []
    const confirmed: ResolvedMember[] = []
    results.forEach((r, index) => {
      const source =
        r.status === "matched" ? r.match : r.status === "ambiguous" ? choices[index] : null
      if (!source) return
      const member = toResolved(source)
      if (member) confirmed.push(member)
    })
    return confirmed
  }

  function handleAddConfirmed() {
    onAdd(buildConfirmed())
    // Reset the panel after adding.
    setResults(null)
    setText("")
    setChoices({})
  }

  const confirmedCount = buildConfirmed().length

  return (
    <div className="space-y-3">
      <textarea
        aria-label="Paste member names or usernames"
        className="w-full rounded-md border px-3 py-2 text-sm leading-snug focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
        disabled={isResolving || disabled}
        onChange={(e) => {
          setText(e.target.value)
          // Clear previous results when the user edits the text.
          if (results !== null) {
            setResults(null)
            setChoices({})
          }
        }}
        placeholder={"Paste names or usernames, one per line or comma-separated"}
        rows={4}
        value={text}
      />
      <div className="flex items-center gap-2">
        <button
          className="rounded-md border px-3 py-1.5 text-sm font-medium disabled:opacity-50"
          disabled={isResolving || parseEntries(text).length === 0}
          onClick={handleResolve}
          type="button"
        >
          {isResolving ? "Resolving..." : "Resolve"}
        </button>
        {results !== null && (
          <button
            className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground disabled:opacity-50"
            disabled={disabled || confirmedCount === 0}
            onClick={handleAddConfirmed}
            type="button"
          >
            Add confirmed matches ({confirmedCount})
          </button>
        )}
      </div>
      {resolveError && (
        <p className="text-sm text-destructive" role="alert">
          {resolveError}
        </p>
      )}
      {results !== null && results.length > 0 && (
        <ul aria-label="Resolve results" className="space-y-2">
          {results.map((r, index) => (
            <li
              key={index}
              className="rounded-md border px-3 py-2 text-sm"
            >
              <span className="font-mono text-xs text-slate-500">{r.entry}</span>
              {r.status === "matched" && r.match && (
                <p className="mt-0.5 text-green-700">
                  <span aria-hidden="true">&#10003; </span>
                  Matched: {r.match.display_name || r.match.username} @{r.match.username}
                </p>
              )}
              {r.status === "ambiguous" && (
                <div className="mt-0.5">
                  <p className="text-amber-700">
                    <span aria-hidden="true">&#9888; </span>
                    Multiple matches
                  </p>
                  <label
                    className="mt-1 block text-xs text-slate-600"
                    htmlFor={`ambiguous-select-${index}`}
                  >
                    Select match for {r.entry}
                  </label>
                  <select
                    className="mt-0.5 w-full rounded border px-2 py-1 text-sm disabled:opacity-50"
                    disabled={disabled}
                    id={`ambiguous-select-${index}`}
                    onChange={(e) => handleChoiceChange(index, e.target.value, r.candidates)}
                    value={choices[index]?.provider_user_id ?? ""}
                  >
                    <option value="">Select a user...</option>
                    {r.candidates.map((c) => (
                      <option key={c.provider_user_id} value={c.provider_user_id}>
                        {c.display_name || c.username} @{c.username}
                      </option>
                    ))}
                  </select>
                </div>
              )}
              {r.status === "unmatched" && (
                <p className="mt-0.5 text-slate-500">
                  <span aria-hidden="true">&#10005; </span>
                  No match
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
      {results !== null && results.length === 0 && (
        <p className="text-sm text-slate-500">No entries to resolve.</p>
      )}
    </div>
  )
}
