// SPDX-License-Identifier: Apache-2.0

import { useEffect, useRef, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"

import { Button } from "@/components/ui/button"
import { Callout } from "@/components/ui/callout"
import { type SignalConfigGroup } from "@/lib/signalConfigGroups"
import { updateTeam, type TeamProfile } from "@/lib/teams"
import { TEAMS_KEY } from "@/lib/teamSetup"

export function SignalGroupAttachList({
  groups,
  team,
}: {
  groups: SignalConfigGroup[]
  team: TeamProfile
}) {
  const queryClient = useQueryClient()
  const [pendingGroupId, setPendingGroupId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Track the intended group IDs optimistically so a rapid toggle on a second group
  // computes the correct next state even before the first write re-fetches.
  const liveIdsRef = useRef<string[]>(team.signal_config_group_ids)

  // Keep in sync with server truth whenever we are idle.
  useEffect(() => {
    if (pendingGroupId === null) {
      liveIdsRef.current = team.signal_config_group_ids
    }
  }, [team.signal_config_group_ids, pendingGroupId])

  const updateMutation = useMutation({
    mutationFn: (signalConfigGroupIds: string[]) =>
      updateTeam(team.id, { signal_config_group_ids: signalConfigGroupIds }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: TEAMS_KEY }),
    onError: () => {
      liveIdsRef.current = team.signal_config_group_ids
      setError("Could not update signal config groups. Please try again.")
    },
    onSettled: () => setPendingGroupId(null),
  })

  function toggleGroup(groupId: string) {
    const attached = liveIdsRef.current.includes(groupId)
    const next = attached
      ? liveIdsRef.current.filter((id) => id !== groupId)
      : [...liveIdsRef.current, groupId]
    // Update the live ref before the state change so subsequent renders use the new value.
    liveIdsRef.current = next
    setPendingGroupId(groupId)
    setError(null)
    updateMutation.mutate(next)
  }

  return (
    <div>
      <h3 className="text-sm font-medium text-slate-700">Signal config groups</h3>
      {error && (
        <Callout className="mt-2" role="alert" variant="error">
          {error}
        </Callout>
      )}
      {groups.length === 0 ? (
        <p className="mt-1 text-sm text-slate-500">No groups available.</p>
      ) : (
        <ul className="mt-2 space-y-2">
          {groups.map((group) => {
            const attached = liveIdsRef.current.includes(group.id)
            const isPending = pendingGroupId === group.id
            return (
              <li
                className="flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm"
                key={group.id}
              >
                <span>{group.name}</span>
                <Button
                  disabled={isPending}
                  onClick={() => toggleGroup(group.id)}
                  size="sm"
                  variant="outline"
                >
                  {attached ? "Detach" : "Attach"}
                </Button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
