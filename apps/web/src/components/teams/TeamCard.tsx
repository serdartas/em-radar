// SPDX-License-Identifier: Apache-2.0

import { useMutation, useQueryClient } from "@tanstack/react-query"

import { CodeSourcePicker } from "@/components/teams/CodeSourcePicker"
import { SignalGroupAttachList } from "@/components/teams/SignalGroupAttachList"
import { TaskBoardPicker } from "@/components/teams/TaskBoardPicker"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { type SourceConnection } from "@/lib/connections"
import { type ScopeDefinition } from "@/lib/scopes"
import { type SignalConfigGroup } from "@/lib/signalConfigGroups"
import { deleteTeam, type TeamProfile } from "@/lib/teams"
import { TEAMS_KEY } from "@/lib/teamSetup"

function teamSummaryText(team: TeamProfile, groups: SignalConfigGroup[]): string {
  const parts: string[] = []

  if (team.scope_ids.length > 0) {
    parts.push(`${team.scope_ids.length} board scope${team.scope_ids.length > 1 ? "s" : ""}`)
  } else {
    parts.push("no board source")
  }

  if (team.code_connection_id) {
    parts.push("code source set")
  } else {
    parts.push("no code source")
  }

  const attachedGroupCount = team.signal_config_group_ids.filter((id) =>
    groups.some((g) => g.id === id),
  ).length
  parts.push(`${attachedGroupCount} signal group${attachedGroupCount !== 1 ? "s" : ""}`)

  return parts.join(" · ")
}

export function TeamCard({
  boardScopes,
  codeConnections,
  groups,
  isEditing,
  jiraConnections,
  onDone,
  onStartEdit,
  team,
}: {
  boardScopes: ScopeDefinition[]
  codeConnections: SourceConnection[]
  groups: SignalConfigGroup[]
  /** Controlled by TeamsPage (keyed by team.id) so edit state survives updated_at remounts. */
  isEditing: boolean
  jiraConnections: SourceConnection[]
  onDone: () => void
  onStartEdit: () => void
  team: TeamProfile
}) {
  const queryClient = useQueryClient()

  const deleteMutation = useMutation({
    mutationFn: () => deleteTeam(team.id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: TEAMS_KEY }),
  })

  return (
    <Card>
      <CardContent className="space-y-4 p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">{team.name}</h2>
            {!isEditing && (
              <p className="mt-0.5 text-sm text-slate-500">{teamSummaryText(team, groups)}</p>
            )}
          </div>
          <div className="flex shrink-0 gap-2">
            {isEditing ? (
              <Button
                aria-label={`Done editing ${team.name}`}
                onClick={onDone}
                size="sm"
                variant="outline"
              >
                Done
              </Button>
            ) : (
              <Button
                aria-label={`Edit ${team.name}`}
                onClick={onStartEdit}
                size="sm"
                variant="outline"
              >
                Edit
              </Button>
            )}
            <Button
              disabled={deleteMutation.isPending}
              onClick={() => deleteMutation.mutate()}
              size="sm"
              variant="outline"
            >
              Delete team
            </Button>
          </div>
        </div>

        {isEditing && (
          <>
            <TaskBoardPicker
              boardScopes={boardScopes}
              jiraConnections={jiraConnections}
              team={team}
            />
            <CodeSourcePicker codeConnections={codeConnections} team={team} />
            <SignalGroupAttachList groups={groups} team={team} />
          </>
        )}
      </CardContent>
    </Card>
  )
}
