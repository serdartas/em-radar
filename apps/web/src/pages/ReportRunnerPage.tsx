// SPDX-License-Identifier: Apache-2.0

import { useEffect, useMemo, useState } from "react"
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Select } from "@/components/ui/select"
import { apiErrorMessage } from "@/lib/api"
import {
  enqueueTeamReport,
  getJob,
  getTeamSprints,
  listJobs,
  parseApiTimestamp,
  type ReportJob,
  useFormatTimestamp,
} from "@/lib/reports"
import { listTeams, teamHasNoSources } from "@/lib/teams"

type WindowMode = "date_range" | "sprint"

interface TeamRunInput {
  teamIds: string[]
  window?: { start: string; end: string }
  sprintExternalId?: string
}

const JOB_POLL_MS = 3000

function jobRuntime(job: ReportJob): string | null {
  if (!job.started_at || !job.finished_at) return null
  const ms =
    parseApiTimestamp(job.finished_at).valueOf() - parseApiTimestamp(job.started_at).valueOf()
  if (Number.isNaN(ms) || ms < 0) return null
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`
}

const STATUS_LABEL: Record<ReportJob["status"], string> = {
  queued: "Queued",
  running: "Running",
  done: "Done",
  failed: "Failed",
}

function isTerminal(status: ReportJob["status"]): boolean {
  return status === "done" || status === "failed"
}

export function ReportRunnerPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const formatTs = useFormatTimestamp()
  const teamsQuery = useQuery({ queryKey: ["teams"], queryFn: listTeams })
  const [selectedTeamIds, setSelectedTeamIds] = useState<string[]>([])
  const [windowMode, setWindowMode] = useState<WindowMode>("date_range")
  const [startDate, setStartDate] = useState("")
  const [endDate, setEndDate] = useState("")
  const [selectedSprintExternalId, setSelectedSprintExternalId] = useState("")
  const [dateError, setDateError] = useState<string | null>(null)
  const [enqueueError, setEnqueueError] = useState<string | null>(null)
  // IDs of jobs we enqueued in this session; cleared once they reach terminal state.
  const [pendingJobIds, setPendingJobIds] = useState<string[]>([])

  const teams = teamsQuery.data ?? []

  // Sprint mode is only valid when every selected team uses scrum. Kanban teams (and multi-team
  // selections that include at least one kanban team) fall back to date-range mode.
  const sprintAllowed = useMemo(() => {
    const loadedTeams = teamsQuery.data ?? []
    return (
      selectedTeamIds.length > 0 &&
      selectedTeamIds.every((id) => loadedTeams.find((t) => t.id === id)?.working_mode === "scrum")
    )
  }, [selectedTeamIds, teamsQuery.data])

  // Reset the window mode to date-range whenever sprint is no longer allowed so that the
  // internal state stays consistent with the visible options.
  useEffect(() => {
    if (!sprintAllowed) setWindowMode("date_range")
  }, [sprintAllowed])

  // Clear any previously selected sprint whenever the team selection changes so stale sprint IDs
  // are never carried forward to a different team or a multi-team batch run.
  useEffect(() => {
    setSelectedSprintExternalId("")
  }, [selectedTeamIds])

  // Fetch sprints for the picker when exactly one team is selected in sprint mode.
  const sprintFetchTeamId =
    windowMode === "sprint" && selectedTeamIds.length === 1 ? selectedTeamIds[0] : null
  const sprintsQuery = useQuery({
    queryKey: ["team-sprints", sprintFetchTeamId],
    queryFn: () => getTeamSprints(sprintFetchTeamId!),
    enabled: sprintFetchTeamId !== null,
  })

  // Display list: poll the jobs endpoint and refresh while any listed job is non-terminal.
  const jobsQuery = useQuery({
    queryKey: ["report-jobs"],
    queryFn: listJobs,
    refetchInterval: (query) => {
      const hasRunning = query.state.data?.some((j: ReportJob) => !isTerminal(j.status)) ?? false
      return hasRunning ? JOB_POLL_MS : false
    },
  })
  const jobs = useMemo(() => jobsQuery.data ?? [], [jobsQuery.data])

  // Per-job polling for pending IDs — each job is fetched individually so that batches
  // larger than the list endpoint's terminal limit are still tracked to completion.
  const pendingJobQueries = useQueries({
    queries: pendingJobIds.map((id) => ({
      queryKey: ["report-job", id] as const,
      queryFn: () => getJob(id),
      refetchInterval: (query: { state: { data: ReportJob | undefined } }) =>
        isTerminal(query.state.data?.status ?? "queued") ? false : JOB_POLL_MS,
    })),
  })

  // Navigate when all pending per-job queries reach terminal states.
  useEffect(() => {
    if (pendingJobIds.length === 0) return
    const settled = pendingJobQueries
      .map((q) => q.data)
      .filter((j): j is ReportJob => j !== undefined)

    if (settled.length !== pendingJobIds.length) return // not all fetched yet
    if (!settled.every((j) => isTerminal(j.status))) return // still running

    // Don't navigate if there are outstanding enqueue errors — keep the user on
    // the runner page so they can see both the error and any completed jobs.
    if (enqueueError) {
      setPendingJobIds([])
      void queryClient.invalidateQueries({ queryKey: ["report-jobs"] })
      return
    }

    setPendingJobIds([])
    void queryClient.invalidateQueries({ queryKey: ["report-jobs"] })

    if (settled.length === 1) {
      const job = settled[0]
      if (job.status === "done" && job.report_id) {
        navigate(`/reports/results/${job.report_id}`)
      }
      // On failure: stay on runner so the user sees the failed job.
    } else {
      // Multi-team: only navigate when all succeeded; on any failure stay on runner.
      if (settled.every((j) => j.status === "done")) {
        navigate("/reports/results")
      }
    }
  }, [pendingJobIds, pendingJobQueries, enqueueError, navigate, queryClient])

  const teamRun = useMutation({
    mutationFn: async ({ teamIds, window, sprintExternalId }: TeamRunInput): Promise<ReportJob[]> => {
      const results = await Promise.allSettled(
        teamIds.map((id) => enqueueTeamReport(id, window, sprintExternalId)),
      )
      const accepted: ReportJob[] = []
      const errors: string[] = []
      for (const r of results) {
        if (r.status === "fulfilled") {
          accepted.push(r.value)
        } else {
          errors.push(apiErrorMessage(r.reason, "Failed to enqueue a report run."))
        }
      }
      if (errors.length > 0) {
        setEnqueueError(errors.join(" "))
      }
      return accepted
    },
    onSuccess: (enqueuedJobs: ReportJob[]) => {
      void queryClient.invalidateQueries({ queryKey: ["report-jobs"] })
      if (enqueuedJobs.length > 0) {
        const newIds = enqueuedJobs.map((j) => j.id)
        setPendingJobIds((prev) => [...prev, ...newIds])
      }
    },
    onError: (err: unknown) => {
      setEnqueueError(apiErrorMessage(err, "Failed to start the report run. Please try again."))
    },
  })

  const running = teamRun.isPending

  function toggleTeam(teamId: string) {
    setSelectedTeamIds((current) =>
      current.includes(teamId)
        ? current.filter((id) => id !== teamId)
        : [...current, teamId],
    )
  }

  function handleRun() {
    setDateError(null)
    setEnqueueError(null)
    if (windowMode === "sprint") {
      teamRun.mutate({
        teamIds: selectedTeamIds,
        // Only apply explicit sprint selection for single-team runs; multi-team runs use each
        // team's default window because the selected sprint may not exist on every board.
        sprintExternalId:
          selectedTeamIds.length === 1 ? selectedSprintExternalId || undefined : undefined,
      })
      return
    }
    if (!startDate || !endDate) {
      setDateError("Choose both a start and an end date.")
      return
    }
    const start = `${startDate}T00:00:00Z`
    // The evaluation window is half-open [start, end): end is exclusive. Setting end to the
    // next day at midnight UTC means the entire selected end day is included; an item
    // timestamped exactly at the boundary belongs to the next window.
    const endBoundary = new Date(`${endDate}T00:00:00Z`)
    endBoundary.setUTCDate(endBoundary.getUTCDate() + 1)
    const end = endBoundary.toISOString()
    if (start >= end) {
      setDateError("The start date must be before the end date.")
      return
    }
    teamRun.mutate({ teamIds: selectedTeamIds, window: { start, end } })
  }

  return (
    <section aria-labelledby="page-title" className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight" id="page-title">
          Report Runner
        </h1>
        <p className="mt-2 max-w-xl text-slate-600">
          Run a report for one or more teams against each team&apos;s board scope and attached
          signal config groups.
        </p>
      </header>

      <Card>
        <CardContent className="space-y-4 p-4">
          <h2 className="text-lg font-semibold">Run for teams</h2>
          {teamsQuery.isLoading ? (
            <p className="text-sm text-slate-500">Loading teams...</p>
          ) : teams.length === 0 ? (
            <p className="text-sm text-slate-500">No teams yet. Create one on the Teams page.</p>
          ) : (
            <ul className="space-y-2">
              {teams.map((team) => {
                const noSources = teamHasNoSources(team)
                return (
                  <li key={team.id}>
                    <label
                      className={`flex items-center gap-3 rounded-md border px-3 py-2 text-sm${noSources ? " cursor-not-allowed opacity-60" : ""}`}
                    >
                      <input
                        checked={selectedTeamIds.includes(team.id)}
                        disabled={noSources}
                        onChange={() => toggleTeam(team.id)}
                        type="checkbox"
                      />
                      <span>{team.name}</span>
                      {noSources && (
                        <span className="ml-auto text-xs text-slate-400">
                          no sources attached
                        </span>
                      )}
                    </label>
                  </li>
                )
              })}
            </ul>
          )}
          <div className="space-y-3 border-t pt-4">
            <div className="space-y-1">
              <Label htmlFor="window-mode">Window</Label>
              <Select
                className="sm:max-w-xs"
                id="window-mode"
                onChange={(event) => setWindowMode(event.target.value as WindowMode)}
                value={windowMode}
              >
                {sprintAllowed && <option value="sprint">Active sprint</option>}
                <option value="date_range">Date range</option>
              </Select>
            </div>
            {windowMode === "sprint" ? (
              selectedTeamIds.length === 1 ? (
                <div className="space-y-1">
                  <Label htmlFor="sprint-pick">Sprint</Label>
                  <Select
                    className="sm:max-w-xs"
                    id="sprint-pick"
                    onChange={(event) => setSelectedSprintExternalId(event.target.value)}
                    value={selectedSprintExternalId}
                  >
                    <option value="">Active sprint (default)</option>
                    {(sprintsQuery.data ?? []).map((sprint) => (
                      <option key={sprint.external_id} value={sprint.external_id}>
                        {sprint.name}
                      </option>
                    ))}
                  </Select>
                </div>
              ) : (
                <p className="text-xs text-slate-500">
                  Runs each team&apos;s active sprint. Kanban teams use their default rolling window.
                </p>
              )
            ) : (
              <div className="flex flex-col gap-3 sm:flex-row">
                <div className="space-y-1">
                  <Label htmlFor="window-start">Start date</Label>
                  <input
                    className="flex h-9 rounded-md border border-border bg-background px-3 py-1 text-sm shadow-sm"
                    id="window-start"
                    onChange={(event) => setStartDate(event.target.value)}
                    type="date"
                    value={startDate}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="window-end">End date</Label>
                  <input
                    className="flex h-9 rounded-md border border-border bg-background px-3 py-1 text-sm shadow-sm"
                    id="window-end"
                    onChange={(event) => setEndDate(event.target.value)}
                    type="date"
                    value={endDate}
                  />
                </div>
              </div>
            )}
            {dateError && (
              <p className="text-sm text-red-700" role="alert">
                {dateError}
              </p>
            )}
          </div>
          <Button disabled={running || selectedTeamIds.length === 0} onClick={handleRun}>
            {teamRun.isPending ? "Running team reports…" : "Run team reports"}
          </Button>
        </CardContent>
      </Card>

      <div aria-live="polite" className="space-y-4">
        {enqueueError && (
          <p className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700" role="alert">
            {enqueueError}
          </p>
        )}
        {jobs.length > 0 && (
          <Card>
            <CardContent className="p-4">
              <h2 className="mb-3 text-lg font-semibold">Running / recent</h2>
              <ul className="space-y-2 text-sm" aria-label="report jobs">
                {jobs.map((job) => {
                  const teamName =
                    teams.find((t) => t.id === job.team_profile_id)?.name ?? job.team_profile_id
                  return (
                  <li
                    key={job.id}
                    className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md border px-3 py-2"
                  >
                    <span className="font-medium text-slate-800">{teamName}</span>
                    <span
                      className={`font-medium ${job.status === "failed" ? "text-red-700" : job.status === "done" ? "text-green-700" : "text-slate-700"}`}
                    >
                      {STATUS_LABEL[job.status]}
                    </span>
                    {job.started_at && (
                      <span className="text-slate-500">
                        Started: {formatTs(job.started_at)}
                      </span>
                    )}
                    {job.finished_at && (
                      <span className="text-slate-500">
                        Finished: {formatTs(job.finished_at)}
                      </span>
                    )}
                    {jobRuntime(job) && (
                      <span className="text-slate-500">Runtime: {jobRuntime(job)}</span>
                    )}
                    {job.status === "done" && job.report_id && (
                      <Link
                        className="ml-auto text-blue-700 underline-offset-4 hover:underline"
                        to={`/reports/results/${job.report_id}`}
                      >
                        View report
                      </Link>
                    )}
                    {job.status === "failed" && job.error && (
                      <span className="ml-auto text-xs text-red-600">{job.error}</span>
                    )}
                  </li>
                  )
                })}
              </ul>
            </CardContent>
          </Card>
        )}
        <p className="rounded-lg border border-dashed p-4 text-center text-slate-500">
          <Link
            className="font-medium text-blue-700 underline-offset-4 hover:underline"
            to="/reports/results"
          >
            Browse past reports
          </Link>
        </p>
      </div>
    </section>
  )
}
