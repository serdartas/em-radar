import { type ReactNode, useEffect, useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate } from "react-router-dom"

import { SchemaForm } from "@/components/SchemaForm"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Select } from "@/components/ui/select"
import { apiErrorMessage } from "@/lib/api"
import { connectionErrorGuidance } from "@/lib/connectionErrors"
import { type Connector, getConnectors } from "@/lib/connectors"
import {
  type ConnectionDraft,
  type ConnectionTestResult,
  createConnection,
  deleteConnection,
  type JiraBoard,
  type JiraSprint,
  listJiraBoards,
  listJiraProjects,
  listJiraSprints,
  listConnections,
  type SourceConnection,
  testConnectionDraft,
  testExistingConnection,
  updateConnection,
} from "@/lib/connections"
import { isSecret, type JsonSchema } from "@/lib/jsonSchema"
import { runJiraSprintReport } from "@/lib/reports"

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

      <JiraScopeSection connections={connectionsQuery.data ?? []} />

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
                fieldHelp={selectedConnector.name === "jira" ? JIRA_FIELD_HELP : undefined}
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

interface JiraScopeSectionProps {
  connections: SourceConnection[]
}

function JiraScopeSection({ connections }: JiraScopeSectionProps) {
  const jiraConnections = connections.filter((connection) => connection.connector_name === "jira")

  if (jiraConnections.length === 0) {
    return null
  }

  return (
    <section aria-labelledby="jira-scope-title" className="space-y-4">
      <header>
        <h2 className="text-lg font-semibold" id="jira-scope-title">
          Jira project and board
        </h2>
      </header>
      {jiraConnections.map((connection) => (
        <JiraScopePanel connection={connection} key={connection.id} />
      ))}
    </section>
  )
}

interface JiraScopePanelProps {
  connection: SourceConnection
}

function JiraScopePanel({ connection }: JiraScopePanelProps) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [projectExternalId, setProjectExternalId] = useState("")
  const [boardExternalId, setBoardExternalId] = useState("")
  const [workingMode, setWorkingMode] = useState<"kanban" | "scrum">("scrum")
  const [sprintLengthDays, setSprintLengthDays] = useState<number | null>(14)

  const projectsQuery = useQuery({
    queryKey: ["jira-projects", connection.id],
    queryFn: () => listJiraProjects(connection.id),
  })
  const boardsQuery = useQuery({
    enabled: projectExternalId !== "",
    queryKey: ["jira-boards", connection.id, projectExternalId],
    queryFn: () => listJiraBoards(connection.id, projectExternalId),
  })
  const sprintsQuery = useQuery({
    enabled: boardExternalId !== "",
    queryKey: ["jira-sprints", connection.id, boardExternalId],
    queryFn: () => listJiraSprints(connection.id, boardExternalId),
  })
  const runReport = useMutation({
    mutationFn: runJiraSprintReport,
    onSuccess: (report) => {
      void queryClient.invalidateQueries({ queryKey: ["reports"], exact: true })
      navigate(`/reports/results/${report.id}`)
    },
  })

  const projects = useMemo(() => projectsQuery.data ?? [], [projectsQuery.data])
  const boards = useMemo(() => boardsQuery.data ?? [], [boardsQuery.data])
  const sprints = useMemo(() => sprintsQuery.data ?? [], [sprintsQuery.data])
  const selectedProject = projects.find((project) => project.external_id === projectExternalId)
  const selectedBoard = boards.find((board) => board.external_id === boardExternalId)
  const activeSprint = sprints.find((sprint) => sprint.state === "active")
  const detectedSprintLengthDays = sprintLengthFromSprints(sprints)

  useEffect(() => {
    if (projectExternalId === "" && projects.length > 0) {
      setProjectExternalId(projects[0].external_id)
    }
  }, [projectExternalId, projects])

  useEffect(() => {
    setBoardExternalId("")
  }, [projectExternalId])

  useEffect(() => {
    if (boardExternalId === "" && boards.length > 0) {
      setBoardExternalId(boards[0].external_id)
    }
  }, [boardExternalId, boards])

  useEffect(() => {
    if (!selectedBoard) {
      return
    }
    if (selectedBoard.type === "kanban") {
      setWorkingMode("kanban")
      setSprintLengthDays(null)
      return
    }
    setWorkingMode("scrum")
    setSprintLengthDays(detectedSprintLengthDays ?? 14)
  }, [detectedSprintLengthDays, selectedBoard])

  function submitRun() {
    if (!selectedProject || !selectedBoard) {
      return
    }
    runReport.mutate({
      connectionId: connection.id,
      projectExternalId: selectedProject.external_id,
      boardExternalId: selectedBoard.external_id,
      workingMode,
      sprintLengthDays: workingMode === "scrum" ? sprintLengthDays : null,
    })
  }

  return (
    <Card>
      <CardContent className="space-y-5 p-4">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor={`jira-project-${connection.id}`}>Project</Label>
            <Select
              disabled={projectsQuery.isLoading || projects.length === 0}
              id={`jira-project-${connection.id}`}
              onChange={(event) => setProjectExternalId(event.target.value)}
              value={projectExternalId}
            >
              {projects.map((project) => (
                <option key={project.id} value={project.external_id}>
                  {project.key} · {project.name}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={`jira-board-${connection.id}`}>Board</Label>
            <Select
              disabled={boardsQuery.isLoading || boards.length === 0}
              id={`jira-board-${connection.id}`}
              onChange={(event) => setBoardExternalId(event.target.value)}
              value={boardExternalId}
            >
              {boards.map((board) => (
                <option key={board.id} value={board.external_id}>
                  {board.name}
                </option>
              ))}
            </Select>
          </div>
        </div>

        {selectedBoard && (
          <div className="grid gap-4 rounded-md border p-4 md:grid-cols-3">
            <div>
              <p className="text-xs font-medium uppercase text-slate-500">Detected</p>
              <p className="mt-1 text-sm">
                {modeLabel(selectedBoard, detectedSprintLengthDays)}
              </p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={`jira-mode-${connection.id}`}>Working mode</Label>
              <Select
                id={`jira-mode-${connection.id}`}
                onChange={(event) => {
                  const nextMode = event.target.value === "kanban" ? "kanban" : "scrum"
                  setWorkingMode(nextMode)
                  setSprintLengthDays(nextMode === "scrum" ? detectedSprintLengthDays ?? 14 : null)
                }}
                value={workingMode}
              >
                <option value="scrum">Scrum</option>
                <option value="kanban">Kanban</option>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={`jira-sprint-length-${connection.id}`}>Sprint length</Label>
              <input
                className="flex h-10 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
                disabled={workingMode === "kanban"}
                id={`jira-sprint-length-${connection.id}`}
                min={1}
                onChange={(event) => setSprintLengthDays(Number(event.target.value))}
                type="number"
                value={sprintLengthDays ?? ""}
              />
            </div>
          </div>
        )}

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="text-sm text-slate-600">
            {sprintsQuery.isLoading && "Loading recent sprints…"}
            {!sprintsQuery.isLoading && selectedBoard && activeSprint && (
              <span>Active sprint: {activeSprint.name}</span>
            )}
            {!sprintsQuery.isLoading && selectedBoard && !activeSprint && (
              <span>No active sprint found for this board.</span>
            )}
            {(projectsQuery.isError || boardsQuery.isError || sprintsQuery.isError) && (
              <span className="text-red-700">Jira lists could not be loaded.</span>
            )}
          </div>
          <Button
            disabled={!selectedBoard || !activeSprint || runReport.isPending}
            onClick={submitRun}
            type="button"
          >
            {runReport.isPending ? "Running report…" : "Run report"}
          </Button>
        </div>
        {runReport.isError && (
          <p className="text-sm text-red-700" role="alert">
            {apiErrorMessage(runReport.error, "The Jira report failed. Please try again.")}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

function modeLabel(board: JiraBoard, sprintLengthDays: number | null): string {
  if (board.type === "kanban") {
    return "Kanban"
  }
  if (sprintLengthDays !== null) {
    return `Scrum · ${sprintLengthDays} days`
  }
  return board.type === "scrum" ? "Scrum" : "Unknown"
}

function sprintLengthFromSprints(sprints: JiraSprint[]): number | null {
  const lengths = sprints
    .filter((sprint) => sprint.state === "active" || sprint.state === "closed")
    .map((sprint) => {
      if (!sprint.start_date || !sprint.end_date) {
        return null
      }
      const start = Date.parse(sprint.start_date)
      const end = Date.parse(sprint.end_date)
      if (Number.isNaN(start) || Number.isNaN(end) || end <= start) {
        return null
      }
      return Math.round((end - start) / 86_400_000)
    })
    .filter((length): length is number => length !== null)
    .sort((left, right) => left - right)

  if (lengths.length === 0) {
    return null
  }
  return lengths[Math.floor(lengths.length / 2)]
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
