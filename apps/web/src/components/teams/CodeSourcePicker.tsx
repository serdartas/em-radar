// SPDX-License-Identifier: Apache-2.0

import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"

import { Callout } from "@/components/ui/callout"
import { Label } from "@/components/ui/label"
import { Select } from "@/components/ui/select"
import { type SourceConnection } from "@/lib/connections"
import { updateTeam, type TeamProfile } from "@/lib/teams"
import { TEAM_SOURCE_MUTATION_KEY, TEAMS_KEY } from "@/lib/teamSetup"

export function CodeSourcePicker({
  codeConnections,
  team,
}: {
  codeConnections: SourceConnection[]
  team: TeamProfile
}) {
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)

  const updateMutation = useMutation({
    mutationKey: TEAM_SOURCE_MUTATION_KEY,
    mutationFn: (connectionId: string | null) =>
      updateTeam(team.id, { code_connection_id: connectionId }),
    onSuccess: () => {
      setError(null)
      void queryClient.invalidateQueries({ queryKey: TEAMS_KEY })
    },
    onError: () => setError("Could not update the code source. Please try again."),
  })

  if (codeConnections.length === 0) {
    return (
      <div className="space-y-1.5">
        <h3 className="text-sm font-medium text-slate-700">Code source</h3>
        <p className="text-sm text-slate-500">
          No code connections available. Add a GitLab or GitHub connection to attach a code source.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-1.5">
      <Label htmlFor={`code-source-${team.id}`}>Code source</Label>
      <Select
        disabled={updateMutation.isPending}
        id={`code-source-${team.id}`}
        onChange={(event) => {
          setError(null)
          updateMutation.mutate(event.target.value || null)
        }}
        value={team.code_connection_id ?? ""}
      >
        <option value="">No code source</option>
        {codeConnections.map((conn) => (
          <option key={conn.id} value={conn.id}>
            {conn.name}
          </option>
        ))}
      </Select>
      {error && (
        <Callout role="alert" variant="error">
          {error}
        </Callout>
      )}
    </div>
  )
}
