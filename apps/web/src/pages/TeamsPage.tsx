// SPDX-License-Identifier: Apache-2.0

import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"

import { TeamCard } from "@/components/teams/TeamCard"
import { Card, CardContent } from "@/components/ui/card"
import { InlineCreateRow } from "@/components/ui/inline-create-row"
import { createTeam } from "@/lib/teams"
import { TEAMS_KEY, useTeamSetupData } from "@/lib/teamSetup"

export function TeamsPage() {
  const queryClient = useQueryClient()
  const { isLoading, teams, boardScopes, groups, jiraConnections, codeConnections } =
    useTeamSetupData()
  const [name, setName] = useState("")
  // Track which teams are in edit mode by team.id — stable across updated_at remounts.
  const [editingIds, setEditingIds] = useState<Set<string>>(new Set())

  const createMutation = useMutation({
    mutationFn: createTeam,
    onSuccess: () => {
      setName("")
      void queryClient.invalidateQueries({ queryKey: TEAMS_KEY })
    },
  })

  function startEdit(id: string) {
    setEditingIds((prev) => new Set(prev).add(id))
  }

  function stopEdit(id: string) {
    setEditingIds((prev) => {
      const next = new Set(prev)
      next.delete(id)
      return next
    })
  }

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
        <CardContent className="p-4">
          <InlineCreateRow
            actionLabel={createMutation.isPending ? "Creating..." : "Create team"}
            disabled={createMutation.isPending}
            inputId="team-name"
            label="New team name"
            onChange={setName}
            onAction={() => createMutation.mutate({ name: name.trim() })}
            value={name}
          />
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
                isEditing={editingIds.has(team.id)}
                jiraConnections={jiraConnections}
                key={team.updated_at}
                onDone={() => stopEdit(team.id)}
                onStartEdit={() => startEdit(team.id)}
                team={team}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
