import { useEffect, useMemo, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select } from "@/components/ui/select"
import { apiErrorMessage } from "@/lib/api"
import {
  listJiraBoards,
  listJiraProjects,
  listJiraSprints,
  type JiraSprint,
  type SourceConnection,
} from "@/lib/connections"
import { createScope, type ScopeDefinition } from "@/lib/scopes"
import { updateTeam, type TeamProfile, type TeamProfileUpdate, type WorkingMode } from "@/lib/teams"
import { TEAMS_KEY } from "@/lib/teamSetup"

export const DEFAULT_SPRINT_DAYS = 14

export function sprintLengthFromSprints(sprints: JiraSprint[]): number | null {
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

  const createScopeMutation = useMutation({ mutationFn: createScope })
  const updateMutation = useMutation({
    mutationFn: (update: TeamProfileUpdate) => updateTeam(team.id, update),
    onSuccess: invalidateTeams,
  })

  const lastAutoDetectedBoardRef = useRef("")
  const userOverrodeModeRef = useRef(false)

  const [connId, setConnId] = useState("")
  const [projectFilter, setProjectFilter] = useState("")
  const [selectedProjectExternalId, setSelectedProjectExternalId] = useState("")
  const [boardFilter, setBoardFilter] = useState("")
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

  const filteredProjects = useMemo(() => {
    const q = projectFilter.toLowerCase()
    return projects.filter(
      (p) => p.name.toLowerCase().includes(q) || p.key.toLowerCase().includes(q),
    )
  }, [projects, projectFilter])

  const filteredBoards = useMemo(() => {
    const q = boardFilter.toLowerCase()
    return boards.filter((b) => b.name.toLowerCase().includes(q))
  }, [boards, boardFilter])

  const selectedBoard = boards.find((b) => b.external_id === selectedBoardExternalId) ?? null
  const selectedProject = projects.find((p) => p.external_id === selectedProjectExternalId) ?? null
  const detectedSprintLength = useMemo(() => sprintLengthFromSprints(sprints), [sprints])

  useEffect(() => {
    setSelectedBoardExternalId("")
    setBoardFilter("")
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
        <div className="space-y-3 rounded-md border p-3">
          <div className="space-y-1.5">
            <Label htmlFor={`conn-${team.id}`}>Ticketing connection</Label>
            <Select
              id={`conn-${team.id}`}
              onChange={(event) => {
                setConnId(event.target.value)
                setSelectedProjectExternalId("")
                setProjectFilter("")
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
            <div className="space-y-1.5">
              <Label htmlFor={`project-${team.id}`}>Project</Label>
              <Input
                aria-label="Filter projects"
                disabled={projectsQuery.isLoading}
                onChange={(event) => setProjectFilter(event.target.value)}
                placeholder="Filter projects..."
                value={projectFilter}
              />
              <Select
                disabled={projectsQuery.isLoading || projects.length === 0}
                id={`project-${team.id}`}
                onChange={(event) => setSelectedProjectExternalId(event.target.value)}
                value={selectedProjectExternalId}
              >
                <option value="">Select a project</option>
                {filteredProjects.map((project) => (
                  <option key={project.id} value={project.external_id}>
                    {project.key} - {project.name}
                  </option>
                ))}
              </Select>
            </div>
          )}

          {connId !== "" && selectedProjectExternalId !== "" && (
            <div className="space-y-1.5">
              <Label htmlFor={`board-${team.id}`}>Board</Label>
              <Input
                aria-label="Filter boards"
                disabled={boardsQuery.isLoading}
                onChange={(event) => setBoardFilter(event.target.value)}
                placeholder="Filter boards..."
                value={boardFilter}
              />
              <Select
                disabled={boardsQuery.isLoading || boards.length === 0}
                id={`board-${team.id}`}
                onChange={(event) => setSelectedBoardExternalId(event.target.value)}
                value={selectedBoardExternalId}
              >
                <option value="">Select a board</option>
                {filteredBoards.map((board) => (
                  <option key={board.id} value={board.external_id}>
                    {board.name}
                  </option>
                ))}
              </Select>
            </div>
          )}

          {selectedBoard && (
            <div className="grid gap-4 rounded-md bg-slate-50 p-3 md:grid-cols-2">
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
