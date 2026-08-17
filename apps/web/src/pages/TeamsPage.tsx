// SPDX-License-Identifier: Apache-2.0

import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"

import { CodeSourcePicker } from "@/components/teams/CodeSourcePicker"
import { SignalGroupAttachList } from "@/components/teams/SignalGroupAttachList"
import { TaskBoardPicker } from "@/components/teams/TaskBoardPicker"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { type SourceConnection } from "@/lib/connections"
import { type ScopeDefinition } from "@/lib/scopes"
import { type SignalConfigGroup } from "@/lib/signalConfigGroups"
import { createTeam, deleteTeam, type TeamProfile } from "@/lib/teams"
import { TEAMS_KEY, useTeamSetupData } from "@/lib/teamSetup"

export function TeamsPage() {
  const queryClient = useQueryClient()
  const { isLoading, teams, boardScopes, groups, jiraConnections, codeConnections } =
    useTeamSetupData()
  const [name, setName] = useState("")

  const createMutation = useMutation({
    mutationFn: createTeam,
    onSuccess: () => {
      setName("")
      void queryClient.invalidateQueries({ queryKey: TEAMS_KEY })
    },
  })

  return (
    <section aria-labelledby="page-title" className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight" id="page-title">
          Teams
        </h1>
        <p className="mt-2 max-w-2xl text-slate-600">
          Each team owns a single Jira board scope and attaches signal config groups. Reports run
          per team against that scope and the union of its groups.
        </p>
      </header>

      <Card>
        <CardContent className="flex flex-wrap items-end gap-3 p-4">
          <div className="space-y-1.5">
            <Label htmlFor="team-name">New team name</Label>
            <input
              className="w-64 rounded-md border px-3 py-2 text-sm"
              id="team-name"
              onChange={(event) => setName(event.target.value)}
              value={name}
            />
          </div>
          <Button
            disabled={createMutation.isPending || name.trim().length === 0}
            onClick={() => createMutation.mutate({ name: name.trim() })}
          >
            {createMutation.isPending ? "Creating..." : "Create team"}
          </Button>
        </CardContent>
      </Card>

      {isLoading ? (
        <p className="text-sm text-slate-500">Loading teams...</p>
      ) : (
        <ul className="space-y-4">
          {teams.map((team) => (
            <li key={team.id}>
              <TeamCard
                boardScopes={boardScopes}
                codeConnections={codeConnections}
                groups={groups}
                jiraConnections={jiraConnections}
                key={team.updated_at}
                team={team}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function TeamCard({
  boardScopes,
  codeConnections,
  groups,
  jiraConnections,
  team,
}: {
  boardScopes: ScopeDefinition[]
  codeConnections: SourceConnection[]
  groups: SignalConfigGroup[]
  jiraConnections: SourceConnection[]
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
          <h2 className="text-lg font-semibold">{team.name}</h2>
          <Button onClick={() => deleteMutation.mutate()} size="sm" variant="outline">
            Delete team
          </Button>
        </div>

        <TaskBoardPicker
          boardScopes={boardScopes}
          jiraConnections={jiraConnections}
          team={team}
        />

        <CodeSourcePicker codeConnections={codeConnections} team={team} />

        <SignalGroupAttachList groups={groups} team={team} />
      </CardContent>
    </Card>
  )
}
