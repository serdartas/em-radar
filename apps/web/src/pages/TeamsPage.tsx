import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Select } from "@/components/ui/select"
import { listScopes, type ScopeDefinition } from "@/lib/scopes"
import {
  listSignalConfigGroups,
  type SignalConfigGroup,
} from "@/lib/signalConfigGroups"
import {
  createTeam,
  deleteTeam,
  listTeams,
  updateTeam,
  type TeamProfile,
} from "@/lib/teams"

const TEAMS_KEY = ["teams"]

export function TeamsPage() {
  const queryClient = useQueryClient()
  const teamsQuery = useQuery({ queryKey: TEAMS_KEY, queryFn: listTeams })
  const scopesQuery = useQuery({ queryKey: ["scopes"], queryFn: listScopes })
  const groupsQuery = useQuery({
    queryKey: ["signal-config-groups"],
    queryFn: listSignalConfigGroups,
  })
  const [name, setName] = useState("")

  const createMutation = useMutation({
    mutationFn: createTeam,
    onSuccess: () => {
      setName("")
      void queryClient.invalidateQueries({ queryKey: TEAMS_KEY })
    },
  })

  const loading = teamsQuery.isLoading || scopesQuery.isLoading || groupsQuery.isLoading
  const teams = teamsQuery.data ?? []
  const boardScopes = (scopesQuery.data ?? []).filter((scope) => scope.scope_type === "board")
  const groups = groupsQuery.data ?? []

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

      {loading ? (
        <p className="text-sm text-slate-500">Loading teams...</p>
      ) : (
        <ul className="space-y-4">
          {teams.map((team) => (
            <li key={team.id}>
              <TeamCard
                boardScopes={boardScopes}
                groups={groups}
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
  groups,
  team,
}: {
  boardScopes: ScopeDefinition[]
  groups: SignalConfigGroup[]
  team: TeamProfile
}) {
  const queryClient = useQueryClient()
  const invalidate = () => void queryClient.invalidateQueries({ queryKey: TEAMS_KEY })
  const updateMutation = useMutation({
    mutationFn: (update: Parameters<typeof updateTeam>[1]) => updateTeam(team.id, update),
    onSuccess: invalidate,
  })
  const deleteMutation = useMutation({
    mutationFn: () => deleteTeam(team.id),
    onSuccess: invalidate,
  })

  const boardScopeId = boardScopes.find((scope) => team.scope_ids.includes(scope.id))?.id ?? ""

  function setBoardScope(scopeId: string) {
    const scope = boardScopes.find((item) => item.id === scopeId)
    if (!scope) {
      updateMutation.mutate({ connection_ids: [], scope_ids: [] })
      return
    }
    updateMutation.mutate({ connection_ids: [scope.connection_id], scope_ids: [scope.id] })
  }

  function toggleGroup(groupId: string, attached: boolean) {
    const next = attached
      ? team.signal_config_group_ids.filter((id) => id !== groupId)
      : [...team.signal_config_group_ids, groupId]
    updateMutation.mutate({ signal_config_group_ids: next })
  }

  return (
    <Card>
      <CardContent className="space-y-4 p-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-lg font-semibold">{team.name}</h2>
          <Button onClick={() => deleteMutation.mutate()} size="sm" variant="outline">
            Delete team
          </Button>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor={`board-scope-${team.id}`}>Jira board scope</Label>
          <Select
            id={`board-scope-${team.id}`}
            onChange={(event) => setBoardScope(event.target.value)}
            value={boardScopeId}
          >
            <option value="">No board scope</option>
            {boardScopes.map((scope) => (
              <option key={scope.id} value={scope.id}>
                {scope.name}
              </option>
            ))}
          </Select>
        </div>

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
      </CardContent>
    </Card>
  )
}
