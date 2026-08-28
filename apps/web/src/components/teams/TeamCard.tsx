// SPDX-License-Identifier: Apache-2.0

import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"

import { CodeSourcePicker } from "@/components/teams/CodeSourcePicker"
import { SignalGroupAttachList } from "@/components/teams/SignalGroupAttachList"
import { TaskBoardPicker } from "@/components/teams/TaskBoardPicker"
import { TeamGitLabConfig } from "@/components/teams/TeamGitLabConfig"
import { Button } from "@/components/ui/button"
import { Callout } from "@/components/ui/callout"
import { Card, CardContent } from "@/components/ui/card"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { apiErrorMessage } from "@/lib/api"
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
  hasGitLabConnector,
  isEditing,
  jiraConnections,
  onDone,
  onStartEdit,
  team,
}: {
  boardScopes: ScopeDefinition[]
  codeConnections: SourceConnection[]
  groups: SignalConfigGroup[]
  /** True when at least one MR-capable (GitLab) connection exists in the workspace. */
  hasGitLabConnector: boolean
  /** Controlled by TeamsPage (keyed by team.id) so edit state survives updated_at remounts. */
  isEditing: boolean
  jiraConnections: SourceConnection[]
  onDone: () => void
  onStartEdit: () => void
  team: TeamProfile
}) {
  const queryClient = useQueryClient()
  const [confirmingDelete, setConfirmingDelete] = useState(false)

  const deleteMutation = useMutation({
    mutationFn: () => deleteTeam(team.id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: TEAMS_KEY }),
  })

  return (
    <Card>
      <CardContent className="space-y-4 p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold">{team.name}</h2>
              {hasGitLabConnector && team.gitlab_config_status === "configured" && (
                <span className="rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-800">
                  GitLab configured
                </span>
              )}
              {/* A team with no code source yet (not_applicable) also needs setup now that a
                  GitLab connector exists, so treat anything other than configured as setup-required. */}
              {hasGitLabConnector && team.gitlab_config_status !== "configured" && (
                <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-800">
                  GitLab setup required
                </span>
              )}
            </div>
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
              aria-label={`Delete ${team.name}`}
              disabled={deleteMutation.isPending}
              onClick={() => setConfirmingDelete(true)}
              size="sm"
              variant="outline"
            >
              Delete team
            </Button>
          </div>
        </div>

        {confirmingDelete && (
          <ConfirmDialog
            body={`Delete "${team.name}"? This removes the team and its report history. This cannot be undone.`}
            confirmLabel="Delete team"
            onCancel={() => setConfirmingDelete(false)}
            onConfirm={() =>
              deleteMutation.mutate(undefined, { onSettled: () => setConfirmingDelete(false) })
            }
            pending={deleteMutation.isPending}
            title={`Delete ${team.name}`}
          />
        )}

        {deleteMutation.isError && (
          <p className="text-sm text-red-700" role="alert">
            {apiErrorMessage(deleteMutation.error, "Failed to delete the team. Please try again.")}
          </p>
        )}

        {!isEditing && hasGitLabConnector && team.gitlab_config_status !== "configured" && (
          <Callout variant="warning">
            <p>
              {team.gitlab_config_status === "setup_required"
                ? "This team has a GitLab connection but no members or repositories configured yet."
                : "This team has no GitLab code source selected yet."}
            </p>
            <Button className="mt-3" onClick={onStartEdit} size="sm" type="button" variant="outline">
              Configure GitLab
            </Button>
          </Callout>
        )}

        {isEditing && (
          <>
            <TaskBoardPicker
              boardScopes={boardScopes}
              jiraConnections={jiraConnections}
              team={team}
            />
            <CodeSourcePicker codeConnections={codeConnections} team={team} />
            {/* Self-gates: renders nothing unless the team's code connection is MR-capable (§3). */}
            <TeamGitLabConfig codeConnections={codeConnections} team={team} />
            <SignalGroupAttachList groups={groups} team={team} />
          </>
        )}
      </CardContent>
    </Card>
  )
}
