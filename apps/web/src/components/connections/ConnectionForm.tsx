import { type ReactNode, useEffect, useRef, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Link } from "react-router-dom"

import { SchemaForm } from "@/components/SchemaForm"
import { TestResult } from "@/components/connections/TestResult"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select } from "@/components/ui/select"
import { type Connector, SOURCE_TYPES } from "@/lib/connectors"
import {
  type ConnectionDraft,
  connectionErrorMessage,
  createConnection,
  type SourceConnection,
  testConnectionDraft,
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

function writableValues(
  schema: JsonSchema,
  values: Record<string, unknown>,
): Record<string, unknown> {
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

interface ConnectionFormProps {
  connectors: Connector[]
  editing?: SourceConnection | null
  onSaved?: (connection: SourceConnection) => void
  onCancel?: () => void
  lockConnectorName?: string
}

export function ConnectionForm({
  connectors,
  editing = null,
  onSaved,
  onCancel,
  lockConnectorName,
}: ConnectionFormProps) {
  const queryClient = useQueryClient()
  const implementedNames = new Set(connectors.map((connector) => connector.name))
  const [connectorName, setConnectorName] = useState("")
  const [connectionName, setConnectionName] = useState("")
  const [values, setValues] = useState<Record<string, unknown>>({})

  const testMutation = useMutation({ mutationFn: testConnectionDraft })
  const saveMutation = useMutation({
    mutationFn: (draft: ConnectionDraft) =>
      editing ? updateConnection(editing.id, draft) : createConnection(draft),
    onSuccess: (created) => {
      void queryClient.invalidateQueries({ queryKey: ["connections"] })
      const connector = connectors.find((c) => c.name === (lockConnectorName ?? connectorName))
      setConnectionName("")
      setValues(connector ? defaultValues(connector.config_schema) : {})
      testMutation.reset()
      onSaved?.(created)
    },
  })

  const selectedConnector = connectors.find((connector) => connector.name === connectorName)
  const prevEditingIdRef = useRef<string | null>(null)

  useEffect(() => {
    const prevEditingId = prevEditingIdRef.current
    prevEditingIdRef.current = editing?.id ?? null

    if (editing) {
      const connector = connectors.find((c) => c.name === editing.connector_name)
      setConnectorName(editing.connector_name)
      setConnectionName(editing.name)
      setValues(connector ? editValues(connector.config_schema, editing.config) : editing.config)
      testMutation.reset()
      return
    }

    const addTarget = lockConnectorName ?? SOURCE_TYPES.find((t) => implementedNames.has(t.name))?.name
    const addConnector = addTarget ? connectors.find((c) => c.name === addTarget) : undefined

    // Leaving edit mode (Cancel): wipe the edited connection's fields so a later submit does not
    // create a new connection from the abandoned edit.
    if (prevEditingId !== null) {
      setConnectorName(addTarget ?? "")
      setConnectionName("")
      setValues(addConnector ? defaultValues(addConnector.config_schema) : {})
      testMutation.reset()
      return
    }

    // Initial mount in add mode: pick a default connector without clobbering an in-progress add.
    if (connectorName === "" && addTarget) {
      setConnectorName(addTarget)
      setValues(addConnector ? defaultValues(addConnector.config_schema) : {})
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editing, connectors, lockConnectorName])

  function pickConnector(name: string) {
    const connector = connectors.find((candidate) => candidate.name === name)
    setConnectorName(name)
    setValues(connector ? defaultValues(connector.config_schema) : {})
    testMutation.reset()
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
      config: editing ? writableValues(selectedConnector.config_schema, values) : values,
    })
  }

  const submitDisabled =
    !selectedConnector || connectionName.trim() === "" || saveMutation.isPending

  return (
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
            {editing ? "Edit connection" : "Add connection"}
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

          {lockConnectorName === undefined && (
            <div className="space-y-1.5">
              <Label htmlFor="connector-select">Source type</Label>
              <Select
                disabled={editing !== null || connectors.length === 0}
                id="connector-select"
                onChange={(event) => pickConnector(event.target.value)}
                value={connectorName}
              >
                {SOURCE_TYPES.map((sourceType) => {
                  const implemented = implementedNames.has(sourceType.name)
                  return (
                    <option disabled={!implemented} key={sourceType.name} value={sourceType.name}>
                      {implemented ? sourceType.label : `${sourceType.label} (coming soon)`}
                    </option>
                  )
                })}
              </Select>
            </div>
          )}

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
                testMutation.mutate({
                  name: connectionName,
                  connector_name: connectorName,
                  config: values,
                })
              }
              type="button"
              variant="outline"
            >
              {testMutation.isPending ? "Testing…" : "Test connection"}
            </Button>
            <Button disabled={submitDisabled} type="submit">
              {saveMutation.isPending
                ? "Saving…"
                : editing
                  ? "Save connection"
                  : "Add connection"}
            </Button>
            {editing && onCancel && (
              <Button onClick={onCancel} type="button" variant="outline">
                Cancel
              </Button>
            )}
          </div>
          {saveMutation.isError && (
            <p className="text-sm text-red-700" role="alert">
              {connectionErrorMessage(saveMutation.error)}
            </p>
          )}
        </CardContent>
      </form>
    </Card>
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
        enter the exact label text and status name your team uses (e.g.{" "}
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
      <code className="rounded bg-blue-100 px-1">read_api</code> scope - that is the only scope
      EM Radar needs. Create one under Preferences &rarr; Access Tokens for an account that can see
      the projects you report on.{" "}
      <Link className="font-medium underline" to="/help/gitlab">
        How to generate a GitLab token
      </Link>
      .
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
