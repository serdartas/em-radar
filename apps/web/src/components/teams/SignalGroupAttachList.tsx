// SPDX-License-Identifier: Apache-2.0

import { useMutation, useQueryClient } from "@tanstack/react-query"

import { Button } from "@/components/ui/button"
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
  const updateMutation = useMutation({
    mutationFn: (signalConfigGroupIds: string[]) =>
      updateTeam(team.id, { signal_config_group_ids: signalConfigGroupIds }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: TEAMS_KEY }),
  })

  function toggleGroup(groupId: string, attached: boolean) {
    const next = attached
      ? team.signal_config_group_ids.filter((id) => id !== groupId)
      : [...team.signal_config_group_ids, groupId]
    updateMutation.mutate(next)
  }

  return (
    <div>
      <h3 className="text-sm font-medium text-slate-700">Signal config groups</h3>
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
                <Button
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
