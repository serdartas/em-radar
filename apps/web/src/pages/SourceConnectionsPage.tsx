import { useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { ConnectionForm } from "@/components/connections/ConnectionForm"
import { TestResult } from "@/components/connections/TestResult"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { ApiError } from "@/lib/api"
import { type Connector, getConnectors } from "@/lib/connectors"
import {
  type ConnectionConflict,
  deleteConnection,
  listConnections,
  type SourceConnection,
  testExistingConnection,
} from "@/lib/connections"

export function SourceConnectionsPage() {
  const connectorsQuery = useQuery({ queryKey: ["connectors"], queryFn: getConnectors })
  const connectionsQuery = useQuery({ queryKey: ["connections"], queryFn: listConnections })

  const connectors = useMemo(() => connectorsQuery.data ?? [], [connectorsQuery.data])
  const [editing, setEditing] = useState<SourceConnection | null>(null)

  return (
    <section aria-labelledby="page-title" className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight" id="page-title">
          Source Connections
        </h1>
        <p className="mt-2 max-w-2xl text-slate-600">
          Connect EM Radar to your Jira and GitLab instances. Tokens are stored locally and shown
          masked.
        </p>
      </header>

      <ConnectionList
        connections={connectionsQuery.data ?? []}
        connectors={connectors}
        isLoading={connectionsQuery.isLoading}
        onEdit={setEditing}
      />

      <ConnectionForm
        connectors={connectors}
        editing={editing}
        onCancel={() => setEditing(null)}
        onSaved={() => setEditing(null)}
      />
    </section>
  )
}

interface ConnectionListProps {
  connections: SourceConnection[]
  connectors: Connector[]
  isLoading: boolean
  onEdit: (connection: SourceConnection) => void
}

function ConnectionList({ connections, connectors, isLoading, onEdit }: ConnectionListProps) {
  if (isLoading) {
    return <p className="text-sm text-slate-500">Loading connections&hellip;</p>
  }

  if (connections.length === 0) {
    return (
      <p className="rounded-lg border border-dashed p-6 text-center text-sm text-slate-500">
        No connections yet. Add one below.
      </p>
    )
  }

  return (
    <ul aria-label="Existing connections" className="space-y-3">
      {connections.map((connection) => {
        const connector = connectors.find(
          (candidate) => candidate.name === connection.connector_name,
        )
        return (
          <ConnectionRow
            connection={connection}
            displayName={connector?.display_name ?? connection.connector_name}
            key={connection.id}
            onEdit={onEdit}
          />
        )
      })}
    </ul>
  )
}

interface ConnectionRowProps {
  connection: SourceConnection
  displayName: string
  onEdit: (connection: SourceConnection) => void
}

function ConnectionRow({ connection, displayName, onEdit }: ConnectionRowProps) {
  const queryClient = useQueryClient()
  const [confirming, setConfirming] = useState(false)
  const [conflict, setConflict] = useState<ConnectionConflict | null>(null)

  const retest = useMutation({ mutationFn: () => testExistingConnection(connection.id) })

  const deleteMutation = useMutation({
    mutationFn: (force: boolean) => deleteConnection(connection.id, force),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["connections"] })
      setConfirming(false)
      setConflict(null)
    },
    onError: (error: unknown) => {
      if (
        error instanceof ApiError &&
        error.status === 409 &&
        typeof error.detail === "object" &&
        error.detail !== null &&
        "dependent_teams" in error.detail
      ) {
        setConflict(error.detail as ConnectionConflict)
      }
    },
  })

  const entries = Object.entries(connection.config)

  return (
    <li>
      <Card>
        <CardContent className="flex flex-col gap-4 p-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 space-y-1">
            <p className="font-medium">{connection.name}</p>
            <p className="text-sm text-slate-500">{displayName}</p>
            {entries.length > 0 && (
              <dl className="text-xs text-slate-500">
                {entries.map(([key, value]) => (
                  <div className="flex gap-1" key={key}>
                    <dt className="font-medium">{key}:</dt>
                    <dd className="truncate">{String(value)}</dd>
                  </div>
                ))}
              </dl>
            )}
            <TestResult error={retest.error} result={retest.data} />
          </div>
          <div className="flex shrink-0 flex-wrap gap-2">
            <Button onClick={() => retest.mutate()} size="sm" variant="outline">
              {retest.isPending ? "Testing…" : "Re-test"}
            </Button>
            <Button onClick={() => onEdit(connection)} size="sm" variant="outline">
              Edit
            </Button>
            {!confirming && (
              <Button
                onClick={() => {
                  setConfirming(true)
                  setConflict(null)
                }}
                size="sm"
                variant="outline"
              >
                Delete
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {confirming && (
        <div
          aria-label={`Confirm: Delete connection ${connection.name}`}
          className="mt-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
          role="alertdialog"
        >
          {conflict ? (
            <>
              {conflict.dependent_teams.length > 0 ? (
                <>
                  <p className="font-medium">This connection is used by the following teams:</p>
                  <ul className="mt-1 list-disc pl-4">
                    {conflict.dependent_teams.map((t) => (
                      <li key={t.id}>{t.name}</li>
                    ))}
                  </ul>
                </>
              ) : (
                <p className="font-medium">
                  This connection has scope definitions that will be removed.
                </p>
              )}
              <p className="mt-2">
                Proceeding will remove the connection, its cached data, and all references to it.
                This cannot be undone.
              </p>
            </>
          ) : (
            <p>
              This removes the connection and all cached source data for it. This cannot be undone.
            </p>
          )}
          <div className="mt-3 flex gap-2">
            <Button
              disabled={deleteMutation.isPending}
              onClick={() => deleteMutation.mutate(conflict !== null)}
              size="sm"
            >
              {conflict ? "Confirm force delete" : "Confirm delete"}
            </Button>
            <Button
              onClick={() => {
                setConfirming(false)
                setConflict(null)
              }}
              size="sm"
              variant="outline"
            >
              Cancel
            </Button>
          </div>
        </div>
      )}
    </li>
  )
}
