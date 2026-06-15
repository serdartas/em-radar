import { useEffect, useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { SchemaForm } from "@/components/SchemaForm"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Select } from "@/components/ui/select"
import { apiErrorMessage } from "@/lib/api"
import { type Connector, getConnectors } from "@/lib/connectors"
import {
  type ConnectionDraft,
  type ConnectionTestResult,
  createConnection,
  deleteConnection,
  listConnections,
  type SourceConnection,
  testConnectionDraft,
  testExistingConnection,
  updateConnection,
} from "@/lib/connections"
import { isSecret, type JsonSchema } from "@/lib/jsonSchema"

function defaultValues(schema: JsonSchema): Record<string, unknown> {
  const values: Record<string, unknown> = {}
  for (const [key, property] of Object.entries(schema.properties ?? {})) {
    if (property.default !== undefined) {
      values[key] = property.default
    }
  }
  return values
}

function editValues(schema: JsonSchema, config: Record<string, unknown>): Record<string, unknown> {
  const values: Record<string, unknown> = { ...config }
  for (const [key, property] of Object.entries(schema.properties ?? {})) {
    if (isSecret(property)) {
      values[key] = ""
    }
  }
  return values
}

function writableValues(schema: JsonSchema, values: Record<string, unknown>): Record<string, unknown> {
  const next: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(values)) {
    const property = schema.properties?.[key]
    if (property && isSecret(property) && value === "") {
      continue
    }
    next[key] = value
  }
  return next
}

function errorMessage(error: unknown): string {
  return apiErrorMessage(error, "The connection could not be reached. Check the URL and try again.")
}

export function SourceConnectionsPage() {
  const queryClient = useQueryClient()
  const connectorsQuery = useQuery({ queryKey: ["connectors"], queryFn: getConnectors })
  const connectionsQuery = useQuery({ queryKey: ["connections"], queryFn: listConnections })

  const connectors = useMemo(() => connectorsQuery.data ?? [], [connectorsQuery.data])
  const [connectorName, setConnectorName] = useState("")
  const [values, setValues] = useState<Record<string, unknown>>({})
  const [editingId, setEditingId] = useState<string | null>(null)

  const selectedConnector = connectors.find((connector) => connector.name === connectorName)

  useEffect(() => {
    if (connectorName === "" && connectors.length > 0) {
      setConnectorName(connectors[0].name)
      setValues(defaultValues(connectors[0].config_schema))
    }
  }, [connectorName, connectors])

  const testMutation = useMutation({ mutationFn: testConnectionDraft })
  const saveMutation = useMutation({
    mutationFn: (draft: ConnectionDraft) =>
      editingId ? updateConnection(editingId, draft) : createConnection(draft),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["connections"] })
      resetForm()
    },
  })
  const deleteMutation = useMutation({
    mutationFn: deleteConnection,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["connections"] }),
  })

  function resetForm() {
    setEditingId(null)
    const first = connectors[0]
    if (first) {
      setConnectorName(first.name)
      setValues(defaultValues(first.config_schema))
    }
    testMutation.reset()
  }

  function pickConnector(name: string) {
    const connector = connectors.find((candidate) => candidate.name === name)
    setEditingId(null)
    setConnectorName(name)
    setValues(connector ? defaultValues(connector.config_schema) : {})
    testMutation.reset()
  }

  function startEdit(connection: SourceConnection) {
    const connector = connectors.find((candidate) => candidate.name === connection.connector_name)
    setEditingId(connection.id)
    setConnectorName(connection.connector_name)
    setValues(
      connector ? editValues(connector.config_schema, connection.config) : connection.config,
    )
    testMutation.reset()
  }

  function removeConnection(id: string) {
    if (window.confirm("Delete this connection and its cached data?")) {
      deleteMutation.mutate(id)
    }
  }

  function changeField(key: string, value: unknown) {
    setValues((current) => ({ ...current, [key]: value }))
  }

  function submit() {
    if (!selectedConnector) {
      return
    }
    saveMutation.mutate({
      connector_name: connectorName,
      config: editingId ? writableValues(selectedConnector.config_schema, values) : values,
    })
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

      <ConnectionList
        connections={connectionsQuery.data ?? []}
        connectors={connectors}
        isLoading={connectionsQuery.isLoading}
        onDelete={removeConnection}
        onEdit={startEdit}
      />

      <Card>
        <form
          aria-labelledby="connection-form-title"
          onSubmit={(event) => {
            event.preventDefault()
            submit()
          }}
        >
          <CardHeader>
            <h2 className="text-lg font-semibold" id="connection-form-title">
              {editingId ? "Edit connection" : "Add connection"}
            </h2>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="space-y-1.5">
              <Label htmlFor="connector-select">Source type</Label>
              <Select
                disabled={editingId !== null || connectors.length === 0}
                id="connector-select"
                onChange={(event) => pickConnector(event.target.value)}
                value={connectorName}
              >
                {connectors.map((connector) => (
                  <option key={connector.name} value={connector.name}>
                    {connector.display_name}
                  </option>
                ))}
              </Select>
            </div>

            {selectedConnector && (
              <SchemaForm
                idPrefix="connection"
                onChange={changeField}
                schema={selectedConnector.config_schema}
                values={values}
              />
            )}

            <TestResult error={testMutation.error} result={testMutation.data} />

            <div className="flex flex-wrap gap-3">
              <Button
                disabled={!selectedConnector || testMutation.isPending}
                onClick={() =>
                  testMutation.mutate({ connector_name: connectorName, config: values })
                }
                type="button"
                variant="outline"
              >
                {testMutation.isPending ? "Testing…" : "Test connection"}
              </Button>
              <Button disabled={!selectedConnector || saveMutation.isPending} type="submit">
                {saveMutation.isPending
                  ? "Saving…"
                  : editingId
                    ? "Save connection"
                    : "Add connection"}
              </Button>
              {editingId && (
                <Button onClick={resetForm} type="button" variant="outline">
                  Cancel
                </Button>
              )}
            </div>
            {saveMutation.isError && (
              <p className="text-sm text-red-700" role="alert">
                {errorMessage(saveMutation.error)}
              </p>
            )}
          </CardContent>
        </form>
      </Card>
    </section>
  )
}

interface ConnectionListProps {
  connections: SourceConnection[]
  connectors: Connector[]
  isLoading: boolean
  onEdit: (connection: SourceConnection) => void
  onDelete: (id: string) => void
}

function ConnectionList({
  connections,
  connectors,
  isLoading,
  onDelete,
  onEdit,
}: ConnectionListProps) {
  if (isLoading) {
    return <p className="text-sm text-slate-500">Loading connections…</p>
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
            onDelete={onDelete}
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
  onDelete: (id: string) => void
}

function ConnectionRow({ connection, displayName, onDelete, onEdit }: ConnectionRowProps) {
  const retest = useMutation({ mutationFn: () => testExistingConnection(connection.id) })
  const entries = Object.entries(connection.config)

  return (
    <li>
      <Card>
        <CardContent className="flex flex-col gap-4 p-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 space-y-1">
            <p className="font-medium">{displayName}</p>
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
            <Button onClick={() => onDelete(connection.id)} size="sm" variant="outline">
              Delete
            </Button>
          </div>
        </CardContent>
      </Card>
    </li>
  )
}

interface TestResultProps {
  error: unknown
  result: ConnectionTestResult | undefined
}

function TestResult({ error, result }: TestResultProps) {
  if (error) {
    return (
      <p
        className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700"
        role="alert"
      >
        {errorMessage(error)}
      </p>
    )
  }
  if (!result) {
    return null
  }
  if (!result.ok) {
    return (
      <p
        className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700"
        role="alert"
      >
        {result.detail}
      </p>
    )
  }
  return (
    <div
      className="rounded-md border border-green-200 bg-green-50 p-3 text-sm text-green-800"
      role="status"
    >
      <p>Connected as {result.user_display_name ?? "the configured user"}.</p>
      {result.permissions.length > 0 && (
        <p className="mt-1 flex flex-wrap items-center gap-1">
          <span>Permissions:</span>
          {result.permissions.map((permission) => (
            <Badge key={permission} variant="info">
              {permission}
            </Badge>
          ))}
        </p>
      )}
    </div>
  )
}
