// SPDX-License-Identifier: Apache-2.0

import { useEffect, useMemo, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { Button } from "@/components/ui/button"
import { Combobox } from "@/components/ui/combobox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select } from "@/components/ui/select"
import { apiErrorMessage } from "@/lib/api"
import {
  listJiraBoards,
  listJiraProjects,
  listJiraSprints,
  type JiraBoard,
  type JiraProject,
  type JiraSprint,
  type SourceConnection,
} from "@/lib/connections"
import { createScope, type ScopeDefinition } from "@/lib/scopes"
import { updateTeam, type TeamProfile, type TeamProfileUpdate, type WorkingMode } from "@/lib/teams"
import { TEAM_SOURCE_MUTATION_KEY, TEAMS_KEY } from "@/lib/teamSetup"

const DEFAULT_SPRINT_DAYS = 14

// Boards dropdown shows this many items on focus/click; all boards remain searchable by typing.
const BOARDS_ON_FOCUS = 5

function sprintLengthFromSprints(sprints: JiraSprint[]): number | null {
  const lengths = sprints
    .filter((sprint) => sprint.state === "active" || sprint.state === "closed")
    .map((sprint) => {
      if (!sprint.start_date || !sprint.end_date) return null
      const start = Date.parse(sprint.start_date)
      const end = Date.parse(sprint.end_date)
      if (Number.isNaN(start) || Number.isNaN(end) || end <= start) return null
      return Math.round((end - start) / 86_400_000)
    })
    .filter((length): length is number => length !== null)
    .sort((a, b) => a - b)
  if (lengths.length === 0) return null
  return lengths[Math.floor(lengths.length / 2)]
}

interface ProjectPickerProps {
  id?: string
  isLoading: boolean
  onSelect: (externalId: string) => void
  projects: JiraProject[]
  value: string
}

export function ProjectPicker({ id, isLoading, onSelect, projects, value }: ProjectPickerProps) {
  const options = useMemo(
    () => projects.map((p) => ({ value: p.external_id, label: `${p.key} - ${p.name}` })),
    [projects],
  )
  return (
    <Combobox
      id={id}
      inputLabel="Project"
      onSelect={onSelect}
      options={options}
      placeholder={isLoading ? "Loading projects..." : "Type to search projects"}
      value={value || undefined}
    />
  )
}

interface BoardPickerProps {
  boards: JiraBoard[]
  id?: string
  isLoading: boolean
  onSelect: (externalId: string) => void
  value: string
}

export function BoardPicker({ boards, id, isLoading, onSelect, value }: BoardPickerProps) {
  const options = useMemo(
    () => boards.map((b) => ({ value: b.external_id, label: b.name })),
    [boards],
  )
  return (
    <Combobox
      id={id}
      inputLabel="Board"
      maxOnFocus={BOARDS_ON_FOCUS}
      onSelect={onSelect}
      options={options}
      placeholder={isLoading ? "Loading boards..." : "Type to search boards"}
      value={value || undefined}
    />
  )
}

export function TaskBoardPicker({
  boardScopes,
  jiraConnections,
  team,
}: {
  boardScopes: ScopeDefinition[]
  jiraConnections: SourceConnection[]
  team: TeamProfile
}) {
  const queryClient = useQueryClient()
  const invalidateTeams = () => void queryClient.invalidateQueries({ queryKey: TEAMS_KEY })

  const createScopeMutation = useMutation({
    mutationKey: TEAM_SOURCE_MUTATION_KEY,
    mutationFn: createScope,
  })
  const updateMutation = useMutation({
    mutationKey: TEAM_SOURCE_MUTATION_KEY,
    mutationFn: (update: TeamProfileUpdate) => updateTeam(team.id, update),
    onSuccess: invalidateTeams,
  })

  const lastAutoDetectedBoardRef = useRef("")
  const userOverrodeModeRef = useRef(false)

  const [connId, setConnId] = useState("")
  const [selectedProjectExternalId, setSelectedProjectExternalId] = useState("")
  const [selectedBoardExternalId, setSelectedBoardExternalId] = useState("")
  const [workingMode, setWorkingMode] = useState<WorkingMode>("scrum")
  const [sprintLengthDays, setSprintLengthDays] = useState<number | null>(DEFAULT_SPRINT_DAYS)

  const currentScope = boardScopes.find((scope) => team.scope_ids.includes(scope.id))

  const projectsQuery = useQuery({
    enabled: connId !== "",
    queryKey: ["jira-projects", connId],
    queryFn: () => listJiraProjects(connId),
  })
  const boardsQuery = useQuery({
    enabled: connId !== "" && selectedProjectExternalId !== "",
    queryKey: ["jira-boards", connId, selectedProjectExternalId],
    queryFn: () => listJiraBoards(connId, selectedProjectExternalId),
  })
  const sprintsQuery = useQuery({
    enabled: connId !== "" && selectedBoardExternalId !== "",
    queryKey: ["jira-sprints", connId, selectedBoardExternalId],
    queryFn: () => listJiraSprints(connId, selectedBoardExternalId),
  })

  const projects = useMemo(() => projectsQuery.data ?? [], [projectsQuery.data])
  const boards = useMemo(() => boardsQuery.data ?? [], [boardsQuery.data])
  const sprints = useMemo(() => sprintsQuery.data ?? [], [sprintsQuery.data])

  const selectedBoard = boards.find((b) => b.external_id === selectedBoardExternalId) ?? null
  const selectedProject = projects.find((p) => p.external_id === selectedProjectExternalId) ?? null
  const detectedSprintLength = useMemo(() => sprintLengthFromSprints(sprints), [sprints])

  useEffect(() => {
    setSelectedBoardExternalId("")
  }, [selectedProjectExternalId])

  useEffect(() => {
    if (!selectedBoard) return

    if (selectedBoardExternalId !== lastAutoDetectedBoardRef.current) {
      lastAutoDetectedBoardRef.current = selectedBoardExternalId
      userOverrodeModeRef.current = false
      if (selectedBoard.type === "kanban") {
        setWorkingMode("kanban")
        setSprintLengthDays(null)
      } else {
        setWorkingMode("scrum")
        setSprintLengthDays(detectedSprintLength ?? DEFAULT_SPRINT_DAYS)
      }
      return
    }

    if (!userOverrodeModeRef.current && selectedBoard.type !== "kanban") {
      setSprintLengthDays(detectedSprintLength ?? DEFAULT_SPRINT_DAYS)
    }
  }, [selectedBoard, selectedBoardExternalId, detectedSprintLength])

  function handleClear() {
    updateMutation.mutate({ connection_ids: [], scope_ids: [] })
  }

  function handleSave() {
    if (!connId || !selectedProjectExternalId || !selectedBoardExternalId) return
    if (!selectedProject || !selectedBoard) return

    const sprintLength = workingMode === "kanban" ? null : sprintLengthDays

    const existingScope = boardScopes.find(
      (scope) =>
        scope.connection_id === connId && scope.external_ref["id"] === selectedBoard.external_id,
    )

    if (existingScope) {
      updateMutation.mutate({
        connection_ids: [connId],
        scope_ids: [existingScope.id],
        working_mode: workingMode,
        sprint_length_days: sprintLength,
      })
      return
    }

    void createScopeMutation
      .mutateAsync({
        connection_id: connId,
        name: `${selectedProject.key} / ${selectedBoard.name}`,
        scope_type: "board",
        external_ref: {
          id: selectedBoard.external_id,
          key: selectedProject.key,
          name: selectedBoard.name,
        },
        capabilities: workingMode === "scrum" ? ["sprint", "statuses"] : ["statuses"],
      })
      .then((created) => {
        void queryClient.invalidateQueries({ queryKey: ["scopes"] })
        updateMutation.mutate({
          connection_ids: [connId],
          scope_ids: [created.id],
          working_mode: workingMode,
          sprint_length_days: sprintLength,
        })
      })
      .catch(() => {
        // Error is surfaced via createScopeMutation.isError; no unhandled rejection.
      })
  }

  const canSave =
    connId !== "" &&
    selectedProjectExternalId !== "" &&
    selectedBoardExternalId !== "" &&
    (workingMode === "kanban" || (sprintLengthDays !== null && sprintLengthDays > 0))

  const isSaving = createScopeMutation.isPending || updateMutation.isPending

  const saveError =
    createScopeMutation.isError || updateMutation.isError
      ? createScopeMutation.isError
        ? apiErrorMessage(
            createScopeMutation.error,
            "Failed to create board scope. Please try again.",
          )
        : apiErrorMessage(updateMutation.error, "Failed to save team. Please try again.")
      : null

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-medium text-slate-700">Task-board source</h3>
        {currentScope && (
          <div className="flex items-center gap-2 text-sm text-slate-600">
            <span>Current: {currentScope.name}</span>
            <Button onClick={handleClear} size="sm" variant="outline">
              Clear board source
            </Button>
          </div>
        )}
      </div>

      {jiraConnections.length === 0 ? (
        <p className="text-sm text-slate-500">
          No Jira connections configured. Add one in Source Connections.
        </p>
      ) : (
        <div className="space-y-4 rounded-md border p-4">
          <div className="max-w-sm space-y-1.5">
            <Label htmlFor={`conn-${team.id}`}>Ticketing connection</Label>
            <Select
              id={`conn-${team.id}`}
              onChange={(event) => {
                setConnId(event.target.value)
                setSelectedProjectExternalId("")
              }}
              value={connId}
            >
              <option value="">Select a connection</option>
              {jiraConnections.map((conn) => (
                <option key={conn.id} value={conn.id}>
                  {conn.name}
                </option>
              ))}
            </Select>
          </div>

          {connId !== "" && (
            <div className="max-w-sm space-y-1.5">
              <Label htmlFor={`project-${team.id}`}>Project</Label>
              <ProjectPicker
                id={`project-${team.id}`}
                isLoading={projectsQuery.isLoading}
                onSelect={setSelectedProjectExternalId}
                projects={projects}
                value={selectedProjectExternalId}
              />
            </div>
          )}

          {connId !== "" && selectedProjectExternalId !== "" && (
            <div className="max-w-sm space-y-1.5">
              <Label htmlFor={`board-${team.id}`}>Board</Label>
              <BoardPicker
                boards={boards}
                id={`board-${team.id}`}
                isLoading={boardsQuery.isLoading}
                onSelect={setSelectedBoardExternalId}
                value={selectedBoardExternalId}
              />
            </div>
          )}

          {selectedBoard && (
            <div className="max-w-sm grid gap-3 rounded-md bg-slate-50 p-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor={`mode-${team.id}`}>Working mode</Label>
                <Select
                  id={`mode-${team.id}`}
                  onChange={(event) => {
                    userOverrodeModeRef.current = true
                    const next = event.target.value === "kanban" ? "kanban" : "scrum"
                    setWorkingMode(next)
                    setSprintLengthDays(
                      next === "scrum" ? (detectedSprintLength ?? DEFAULT_SPRINT_DAYS) : null,
                    )
                  }}
                  value={workingMode}
                >
                  <option value="scrum">Scrum</option>
                  <option value="kanban">Kanban</option>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor={`sprint-length-${team.id}`}>Sprint length (days)</Label>
                <Input
                  disabled={workingMode === "kanban"}
                  id={`sprint-length-${team.id}`}
                  min={1}
                  onChange={(event) => {
                    userOverrodeModeRef.current = true
                    const n = Number(event.target.value)
                    setSprintLengthDays(Number.isFinite(n) && n > 0 ? n : null)
                  }}
                  type="number"
                  value={sprintLengthDays ?? ""}
                />
              </div>
            </div>
          )}

          <Button disabled={!canSave || isSaving} onClick={handleSave} size="sm">
            {isSaving ? "Saving..." : "Save board source"}
          </Button>

          {saveError !== null && (
            <p className="text-sm text-red-700" role="alert">
              {saveError}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
