// SPDX-License-Identifier: Apache-2.0

import { useState } from "react"
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
  const [error, setError] = useState<string | null>(null)

  const updateMutation = useMutation({
    mutationFn: (signalConfigGroupIds: string[]) =>
      updateTeam(team.id, { signal_config_group_ids: signalConfigGroupIds }),
    // Return the invalidateQueries promise so React Query awaits the refetch before
    // clearing isPending. This keeps all buttons locked until fresh data is in the cache,
    // preventing a stale second edit from overwriting the first write.
    onSuccess: () => queryClient.invalidateQueries({ queryKey: TEAMS_KEY }),
    onError: () => {
      setError("Could not update signal config groups. Please try again.")
    },
  })

  function toggleGroup(groupId: string, attached: boolean) {
    const next = attached
      ? team.signal_config_group_ids.filter((id) => id !== groupId)
      : [...team.signal_config_group_ids, groupId]
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
            const attached = team.signal_config_group_ids.includes(group.id)
            return (
              <li
                className="flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm"
                key={group.id}
              >
                <span>{group.name}</span>
                {/* Disable ALL toggle buttons while any write is in-flight to prevent
                    concurrent PATCHes that would race and lose a write. */}
                <Button
                  disabled={updateMutation.isPending}
                  onClick={() => toggleGroup(group.id, attached)}
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
