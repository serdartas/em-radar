import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link } from "react-router-dom"

import { SignalCreateForm } from "@/components/signals/SignalCreateForm"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Switch } from "@/components/ui/switch"
import { apiErrorMessage } from "@/lib/api"
import { getConnectors } from "@/lib/connectors"
import {
  createSignalDefinition,
  deleteSignalDefinition,
  listSignalDefinitions,
  updateSignalDefinition,
  type SignalDefinition,
} from "@/lib/signalDefinitions"

export function SignalSettingsPage() {
  const queryClient = useQueryClient()
  const definitionsQuery = useQuery({
    queryKey: ["signal-definitions"],
    queryFn: listSignalDefinitions,
  })
  const connectorsQuery = useQuery({ queryKey: ["connectors"], queryFn: getConnectors })
  const schema = connectorsQuery.data?.find((connector) => connector.name === "jira")?.signal_schema
  const [creating, setCreating] = useState(false)

  const createMutation = useMutation({
    mutationFn: createSignalDefinition,
    onSuccess: () => {
      setCreating(false)
      void queryClient.invalidateQueries({ queryKey: ["signal-definitions"] })
    },
  })

  if (definitionsQuery.isLoading || connectorsQuery.isLoading) {
    return <p className="text-sm text-slate-500">Loading signals...</p>
  }

  if (!schema) {
    return <p className="text-sm text-red-700">Signals could not be loaded.</p>
  }

  return (
    <section aria-labelledby="page-title" className="space-y-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight" id="page-title">
            Signal Settings
          </h1>
          <p className="mt-2 max-w-2xl text-slate-600">
            Build custom signals from your own rules, then bundle them into groups to attach to
            teams.
          </p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="outline">
            <Link to="/signals/groups">Signal config groups</Link>
          </Button>
          <Button asChild variant="outline">
            <Link to="/signals/import-export">Import / export pack</Link>
          </Button>
          {!creating && (
            <Button
              onClick={() => {
                createMutation.reset()
                setCreating(true)
              }}
            >
              Create new
            </Button>
          )}
        </div>
      </header>

      {creating ? (
        <SignalCreateForm
          errorMessage={
            createMutation.isError
              ? apiErrorMessage(createMutation.error, "Could not save the signal.")
              : null
          }
          fields={schema.fields}
          onCancel={() => setCreating(false)}
          onSave={(definition) => createMutation.mutate(definition)}
          pending={createMutation.isPending}
        />
      ) : (
        <SignalList definitions={definitionsQuery.data ?? []} />
      )}
    </section>
  )
}

function SignalList({ definitions }: { definitions: SignalDefinition[] }) {
  const queryClient = useQueryClient()
  const toggleMutation = useMutation({
    mutationFn: (definition: SignalDefinition) =>
      updateSignalDefinition(definition.id, { enabled: !definition.enabled }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["signal-definitions"] }),
  })
  const deleteMutation = useMutation({
    mutationFn: deleteSignalDefinition,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["signal-definitions"] }),
  })

  if (definitions.length === 0) {
    return (
      <p className="text-sm text-slate-500">
        No signals yet. Use “Create new” to build your first signal.
      </p>
    )
  }

  return (
    <section aria-labelledby="signals-title" className="space-y-3">
      <h2 className="text-lg font-semibold" id="signals-title">
        Signals
      </h2>
      <ul className="space-y-3">
        {definitions.map((definition) => (
          <li key={definition.id}>
            <Card>
              <CardContent className="flex flex-wrap items-center justify-between gap-4 p-4">
                <div>
                  <h3 className="font-semibold">{definition.name}</h3>
                  <p className="mt-1 text-sm text-slate-600">version {definition.version}</p>
                </div>
                <div className="flex items-center gap-3">
                  <Switch
                    aria-label={`Enable ${definition.name}`}
                    checked={definition.enabled}
                    onCheckedChange={() => toggleMutation.mutate(definition)}
                  />
                  <Button
                    onClick={() => toggleMutation.mutate(definition)}
                    size="sm"
                    variant="outline"
                  >
                    {definition.enabled ? "Disable" : "Enable"}
                  </Button>
                  <Button
                    onClick={() => deleteMutation.mutate(definition.id)}
                    size="sm"
                    variant="outline"
                  >
                    Delete
                  </Button>
                </div>
              </CardContent>
            </Card>
          </li>
        ))}
      </ul>
    </section>
  )
}
