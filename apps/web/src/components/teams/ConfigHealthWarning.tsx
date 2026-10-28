// SPDX-License-Identifier: Apache-2.0

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { Callout } from "@/components/ui/callout"
import { apiErrorMessage } from "@/lib/api"
import {
  deleteGitLabMember,
  deleteGitLabRepository,
  listGitLabMembers,
  listGitLabRepositories,
  verifyGitLabConfig,
  type TeamGitLabMember,
  type TeamGitLabRepository,
} from "@/lib/gitlabScope"

export interface ConfigHealthWarningProps {
  teamId: string
  connectionId: string
}

/**
 * Non-blocking config-health callout (§22, §17) surfacing stale GitLab entries.
 *
 * Reads from the shared React Query cache for members and repositories (same keys as
 * the pickers). When stale entries exist, renders an amber warning callout with per-item
 * Remove and Re-verify. When all entries are VERIFIED, renders a compact "Verify config"
 * link so users can pro-actively check even before any entry becomes stale.
 * Returns null only when no members or repositories are configured at all.
 */
export function ConfigHealthWarning({ connectionId: _connectionId, teamId }: ConfigHealthWarningProps) {
  const queryClient = useQueryClient()

  const { data: members = [] } = useQuery({
    queryKey: ["gitlab-members", teamId],
    queryFn: () => listGitLabMembers(teamId),
  })

  const { data: repos = [] } = useQuery({
    queryKey: ["gitlab-repositories", teamId],
    queryFn: () => listGitLabRepositories(teamId),
  })

  const hasAnyEntries = members.length > 0 || repos.length > 0

  const staleMembers = members.filter(
    (m) => m.verification_status === "unavailable" || m.verification_status === "unverified",
  )
  const staleRepos = repos.filter(
    (r) => r.verification_status === "unavailable" || r.verification_status === "unverified",
  )

  const hasStale = staleMembers.length > 0 || staleRepos.length > 0

  const { isPending: isVerifying, mutate: runVerify, error: verifyError } = useMutation({
    mutationFn: () => verifyGitLabConfig(teamId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["gitlab-members", teamId] })
      void queryClient.invalidateQueries({ queryKey: ["gitlab-repositories", teamId] })
    },
  })

  const {
    isPending: isRemovingMember,
    mutate: removeMember,
    error: removeMemberError,
  } = useMutation({
    mutationFn: (memberId: string) => deleteGitLabMember(teamId, memberId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["gitlab-members", teamId] })
    },
  })

  const {
    isPending: isRemovingRepo,
    mutate: removeRepo,
    error: removeRepoError,
  } = useMutation({
    mutationFn: (repoId: string) => deleteGitLabRepository(teamId, repoId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["gitlab-repositories", teamId] })
    },
  })

  if (!hasAnyEntries) {
    return null
  }

  const isBusy = isVerifying || isRemovingMember || isRemovingRepo

  // No stale entries: render a compact link so users can still trigger verification.
  if (!hasStale) {
    return (
      <div className="flex items-center gap-2 text-xs text-slate-500">
        <button
          className="underline hover:no-underline disabled:cursor-not-allowed disabled:opacity-50"
          disabled={isVerifying}
          onClick={() => runVerify()}
          type="button"
        >
          {isVerifying ? "Verifying…" : "Verify config"}
        </button>
        {verifyError && (
          <span className="text-red-600">
            {apiErrorMessage(verifyError, "Verification failed.")}
          </span>
        )}
      </div>
    )
  }

  return (
    <Callout role="alert" title="Configuration health warning" variant="warning">
      <p className="mt-1 text-sm">
        Some configured GitLab entries are no longer reachable. Deleted users are marked
        unavailable; entries from a replaced connection are unverified.
      </p>

      {staleMembers.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-medium uppercase tracking-wide text-amber-800">Members</p>
          <ul className="mt-1 space-y-1">
            {staleMembers.map((m) => (
              <StaleEntry
                key={m.id}
                disabled={isBusy}
                label={m.display_name ? `${m.display_name} @${m.username}` : `@${m.username}`}
                onRemove={() => removeMember(m.id)}
                status={m.verification_status}
              />
            ))}
          </ul>
        </div>
      )}

      {staleRepos.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-medium uppercase tracking-wide text-amber-800">Repositories</p>
          <ul className="mt-1 space-y-1">
            {staleRepos.map((r) => (
              <StaleEntry
                key={r.id}
                disabled={isBusy}
                label={r.path_with_namespace}
                onRemove={() => removeRepo(r.id)}
                status={r.verification_status}
              />
            ))}
          </ul>
        </div>
      )}

      <div className="mt-3 flex items-center gap-3">
        <button
          className="rounded border border-amber-700 px-3 py-1.5 text-xs font-medium text-amber-900 hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={isBusy}
          onClick={() => runVerify()}
          type="button"
        >
          {isVerifying ? "Verifying…" : "Re-verify"}
        </button>
      </div>

      {verifyError && (
        <p className="mt-2 text-xs text-amber-900" role="alert">
          {apiErrorMessage(verifyError, "Verification failed. Please try again.")}
        </p>
      )}
      {(removeMemberError ?? removeRepoError) && (
        <p className="mt-2 text-xs text-amber-900" role="alert">
          {apiErrorMessage(
            removeMemberError ?? removeRepoError!,
            "Failed to remove entry. Please try again.",
          )}
        </p>
      )}
    </Callout>
  )
}

function statusLabel(status: TeamGitLabMember["verification_status"] | TeamGitLabRepository["verification_status"]): string {
  if (status === "unavailable") return "deleted or archived"
  if (status === "unverified") return "unverified (connector replaced)"
  return status
}

function StaleEntry({
  disabled,
  label,
  onRemove,
  status,
}: {
  label: string
  status: string
  onRemove: () => void
  disabled: boolean
}) {
  return (
    <li className="flex items-center justify-between gap-2 text-sm">
      <span>
        <span className="font-medium">{label}</span>
        <span className="ml-1.5 text-xs text-amber-700">({statusLabel(status)})</span>
      </span>
      <button
        className="shrink-0 text-xs text-amber-900 underline hover:no-underline disabled:cursor-not-allowed disabled:opacity-50"
        disabled={disabled}
        onClick={onRemove}
        type="button"
      >
        Remove
      </button>
    </li>
  )
}
