import { type ReactNode, useEffect, useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link } from "react-router-dom"

import { SchemaForm } from "@/components/SchemaForm"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select } from "@/components/ui/select"
import { apiErrorMessage } from "@/lib/api"
import { connectionErrorGuidance } from "@/lib/connectionErrors"
import { type Connector, getConnectors, SOURCE_TYPES } from "@/lib/connectors"
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
  const implementedNames = useMemo(() => new Set(connectors.map((c) => c.name)), [connectors])
  const [connectorName, setConnectorName] = useState("")
  const [connectionName, setConnectionName] = useState("")
  const [values, setValues] = useState<Record<string, unknown>>({})
  const [editingId, setEditingId] = useState<string | null>(null)

  const selectedConnector = connectors.find((connector) => connector.name === connectorName)

  useEffect(() => {
    if (connectorName === "" && connectors.length > 0) {
      const firstImplemented = SOURCE_TYPES.find((t) => implementedNames.has(t.name))
      if (firstImplemented) {
        const connector = connectors.find((c) => c.name === firstImplemented.name)
        setConnectorName(firstImplemented.name)
        setValues(connector ? defaultValues(connector.config_schema) : {})
      }
    }
  }, [connectorName, connectors, implementedNames])

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
    setConnectionName("")
    const firstImplemented = SOURCE_TYPES.find((t) => implementedNames.has(t.name))
    if (firstImplemented) {
      const connector = connectors.find((c) => c.name === firstImplemented.name)
      setConnectorName(firstImplemented.name)
      setValues(connector ? defaultValues(connector.config_schema) : {})
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
    setConnectionName(connection.name)
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
    if (!selectedConnector || connectionName.trim() === "") {
      return
    }
    saveMutation.mutate({
      name: connectionName.trim(),
      connector_name: connectorName,
      config: editingId ? writableValues(selectedConnector.config_schema, values) : values,
    })
  }

  const submitDisabled = !selectedConnector || connectionName.trim() === "" || saveMutation.isPending

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
              <Label htmlFor="connection-name-input">Connection name</Label>
              <Input
                id="connection-name-input"
                onChange={(event) => setConnectionName(event.target.value)}
                placeholder="e.g. Acme Jira"
                required
                value={connectionName}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="connector-select">Source type</Label>
              <Select
                disabled={editingId !== null || connectors.length === 0}
                id="connector-select"
                onChange={(event) => pickConnector(event.target.value)}
                value={connectorName}
              >
                {SOURCE_TYPES.map((sourceType) => {
                  const implemented = implementedNames.has(sourceType.name)
                  return (
                    <option
                      disabled={!implemented}
                      key={sourceType.name}
                      value={sourceType.name}
                    >
                      {implemented ? sourceType.label : `${sourceType.label} (coming soon)`}
                    </option>
                  )
                })}
              </Select>
            </div>

            {selectedConnector && (
              <SchemaForm
                fieldHelp={FIELD_HELP_BY_CONNECTOR[selectedConnector.name]}
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
                  testMutation.mutate({ name: connectionName, connector_name: connectorName, config: values })
                }
                type="button"
                variant="outline"
              >
                {testMutation.isPending ? "Testing…" : "Test connection"}
              </Button>
              <Button disabled={submitDisabled} type="submit">
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

const JIRA_FIELD_HELP: Record<string, ReactNode> = {
  base_url: (
    <p>
      The root URL of your Jira instance. For Jira Cloud this looks like{" "}
      <code className="rounded bg-blue-100 px-1">https://your-org.atlassian.net</code>; for Server
      or Data Center it is your self-hosted address. Open Jira in a browser and copy the address up
      to the domain.
    </p>
  ),
  token: (
    <p>
      Use a read-only API token for an account that can browse the projects and boards you report
      on. Jira Cloud uses your email plus an API token; Server/Data Center uses a Personal Access
      Token.{" "}
      <Link className="font-medium underline" to="/help/jira">
        How to generate a Jira token
      </Link>
      .
    </p>
  ),
  auth_email: (
    <p>
      The email address of the Atlassian account that owns the API token. Jira{" "}
      <strong>Cloud</strong> requires this (it signs in with email + token). Leave it blank for
      Jira <strong>Server / Data Center</strong>, which authenticates with the token alone.
    </p>
  ),
  verify_tls: (
    <p>
      Whether EM Radar checks the server&apos;s TLS (HTTPS) certificate. Keep this on for Jira
      Cloud and any instance with a valid certificate. Only turn it off for a self-hosted server
      that uses a self-signed or internal certificate. Doing so is less secure.
    </p>
  ),
  field_mapping: (
    <>
      <p>
        Advanced. Maps EM Radar concepts to your Jira fields so signals can read story points,
        epics, acceptance criteria, and blocked state.
      </p>
      <p className="mt-1.5">
        <strong>How to use:</strong> for Story points and Epic link, enter the Jira custom-field ID
        (like <code className="rounded bg-blue-100 px-1">customfield_10016</code>), which you can
        find in Jira under Settings → Issues → Custom fields. For Blocked label and Blocked status,
        enter the
        exact label text and status name your team uses (e.g.{" "}
        <code className="rounded bg-blue-100 px-1">blocked</code> /{" "}
        <code className="rounded bg-blue-100 px-1">Blocked</code>). Leave a field blank to turn that
        mapping off.
      </p>
      <p className="mt-1.5">
        The defaults match a standard Jira setup. Change a value only if your instance differs.
      </p>
    </>
  ),
}

const GITLAB_FIELD_HELP: Record<string, ReactNode> = {
  base_url: (
    <p>
      The root URL of your GitLab instance. For GitLab SaaS this is{" "}
      <code className="rounded bg-blue-100 px-1">https://gitlab.com</code>; for a self-managed
      instance it is your self-hosted address. Open GitLab in a browser and copy the address up to
      the domain.
    </p>
  ),
  token: (
    <p>
      Use a <strong>read-only</strong> GitLab personal access token with the{" "}
      <code className="rounded bg-blue-100 px-1">read_api</code> scope. Create one under Preferences
      &rarr; Access Tokens for an account that can see the projects you report on. A read-only token
      keeps EM Radar from making any changes to your GitLab data.
    </p>
  ),
  verify_tls: (
    <p>
      Whether EM Radar checks the server&apos;s TLS (HTTPS) certificate. Keep this on for GitLab
      SaaS and any instance with a valid certificate. Only turn it off for a self-managed server
      that uses a self-signed or internal certificate. Doing so is less secure.
    </p>
  ),
}

const FIELD_HELP_BY_CONNECTOR: Record<string, Record<string, ReactNode>> = {
  jira: JIRA_FIELD_HELP,
  gitlab: GITLAB_FIELD_HELP,
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
    const guidance = connectionErrorGuidance(result.code, result.detail)
    return (
      <div
        className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700"
        role="alert"
      >
        <p className="font-medium">{guidance.explanation}</p>
        {guidance.suggestions.length > 0 && (
          <ul className="mt-1.5 list-disc space-y-0.5 pl-5">
            {guidance.suggestions.map((suggestion) => (
              <li key={suggestion}>{suggestion}</li>
            ))}
          </ul>
        )}
      </div>
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
