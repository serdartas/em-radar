// SPDX-License-Identifier: Apache-2.0

import { useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"

import { AddConnectionPanel } from "@/components/connections/AddConnectionPanel"
import { ConnectionDeleteConfirm } from "@/components/connections/ConnectionDeleteConfirm"
import { ConnectionForm } from "@/components/connections/ConnectionForm"
import { TestResult } from "@/components/connections/TestResult"
import { Button } from "@/components/ui/button"
import { Callout } from "@/components/ui/callout"
import { Card, CardContent } from "@/components/ui/card"
import { type Connector, getConnectors } from "@/lib/connectors"
import { listConnections, type SourceConnection, testExistingConnection } from "@/lib/connections"
import { listTeams } from "@/lib/teams"

export function SourceConnectionsPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const connectorsQuery = useQuery({ queryKey: ["connectors"], queryFn: getConnectors })
  const connectionsQuery = useQuery({ queryKey: ["connections"], queryFn: listConnections })

  const connectors = useMemo(() => connectorsQuery.data ?? [], [connectorsQuery.data])
  const [editing, setEditing] = useState<SourceConnection | null>(null)
  const [notificationCount, setNotificationCount] = useState<number | null>(null)

  const connections = connectionsQuery.data ?? []

  const mrCapableConnectorNames = useMemo(
    () => new Set(connectors.filter((c) => c.capabilities.provides_mergerequests).map((c) => c.name)),
    [connectors],
  )

  function handleNewConnection(conn: SourceConnection) {
    if (!mrCapableConnectorNames.has(conn.connector_name)) return
    void (async () => {
      try {
        const freshTeams = await queryClient.fetchQuery({
          queryKey: ["teams"],
          queryFn: listTeams,
          staleTime: 0,
        })
        const count = freshTeams.filter((t) => t.gitlab_config_status !== "configured").length
        if (count > 0) setNotificationCount(count)
      } catch {
        // Notification is informational; silently skip if teams cannot be fetched.
      }
    })()
  }

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

      {notificationCount !== null && (
        <Callout role="status" title="GitLab connected" variant="info">
          <p>
            {notificationCount === 1
              ? "1 team has no GitLab configuration yet."
              : `${notificationCount} teams have no GitLab configuration yet.`}
          </p>
          <div className="mt-3 flex gap-2">
            <Button
              onClick={() => {
                setNotificationCount(null)
                navigate("/teams")
              }}
              size="sm"
              type="button"
            >
              Set up teams
            </Button>
            <Button
              onClick={() => setNotificationCount(null)}
              size="sm"
              type="button"
              variant="outline"
            >
              Later
            </Button>
          </div>
        </Callout>
      )}

      <ConnectionList
        connections={connections}
        connectors={connectors}
        isLoading={connectionsQuery.isLoading}
        onEdit={setEditing}
      />

      {editing !== null ? (
        <ConnectionForm
          connectors={connectors}
          editing={editing}
          onCancel={() => setEditing(null)}
          onSaved={() => setEditing(null)}
        />
      ) : connectionsQuery.isSuccess ? (
        connections.length > 0 ? (
          <AddConnectionPanel connectors={connectors} onSaved={handleNewConnection} />
        ) : (
          <ConnectionForm connectors={connectors} onSaved={handleNewConnection} />
        )
      ) : null}
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

  const retest = useMutation({ mutationFn: () => testExistingConnection(connection.id) })

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
              <Button onClick={() => setConfirming(true)} size="sm" variant="outline">
                Delete
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {confirming && (
        <ConnectionDeleteConfirm
          className="mt-2"
          connectionId={connection.id}
          connectionName={connection.name}
          onCancel={() => setConfirming(false)}
          onDeleted={() => {
            void queryClient.invalidateQueries({ queryKey: ["connections"] })
            setConfirming(false)
          }}
        />
      )}
    </li>
  )
}
