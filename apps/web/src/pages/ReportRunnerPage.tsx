// SPDX-License-Identifier: Apache-2.0

import { useEffect, useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Select } from "@/components/ui/select"
import { enqueueTeamReport, formatTimestamp, listJobs, type ReportJob } from "@/lib/reports"
import { listTeams, teamHasNoSources } from "@/lib/teams"

type WindowMode = "date_range" | "sprint"

interface TeamRunInput {
  teamIds: string[]
  window?: { start: string; end: string }
}

const JOB_POLL_MS = 3000

function jobRuntime(job: ReportJob): string | null {
  if (!job.started_at || !job.finished_at) return null
  const ms =
    new Date(job.finished_at.endsWith("Z") ? job.finished_at : `${job.finished_at}Z`).valueOf() -
    new Date(job.started_at.endsWith("Z") ? job.started_at : `${job.started_at}Z`).valueOf()
  if (Number.isNaN(ms) || ms < 0) return null
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`
}

const STATUS_LABEL: Record<ReportJob["status"], string> = {
  queued: "Queued",
  running: "Running",
  done: "Done",
  failed: "Failed",
}

export function ReportRunnerPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const teamsQuery = useQuery({ queryKey: ["teams"], queryFn: listTeams })
  const [selectedTeamIds, setSelectedTeamIds] = useState<string[]>([])
  const [windowMode, setWindowMode] = useState<WindowMode>("sprint")
  const [startDate, setStartDate] = useState("")
  const [endDate, setEndDate] = useState("")
  const [dateError, setDateError] = useState<string | null>(null)
  const [singlePendingJobId, setSinglePendingJobId] = useState<string | null>(null)

  const teams = teamsQuery.data ?? []

  const jobsQuery = useQuery({
    queryKey: ["report-jobs"],
    queryFn: listJobs,
    refetchInterval: singlePendingJobId ? JOB_POLL_MS : false,
  })
  const jobs = useMemo(() => jobsQuery.data ?? [], [jobsQuery.data])

  // Navigate when a single-team job reaches a terminal state.
  useEffect(() => {
    if (!singlePendingJobId) return
    const job = jobs.find((j) => j.id === singlePendingJobId)
    if (!job) return
    if (job.status === "done" && job.report_id) {
      setSinglePendingJobId(null)
      navigate(`/reports/results/${job.report_id}`)
    } else if (job.status === "failed") {
      setSinglePendingJobId(null)
    }
  }, [jobs, singlePendingJobId, navigate])

  const teamRun = useMutation({
    mutationFn: async ({ teamIds, window }: TeamRunInput): Promise<ReportJob[]> =>
      Promise.all(teamIds.map((id) => enqueueTeamReport(id, window))),
    onSuccess: (enqueuedJobs: ReportJob[]) => {
      void queryClient.invalidateQueries({ queryKey: ["report-jobs"] })
      if (enqueuedJobs.length === 1) {
        setSinglePendingJobId(enqueuedJobs[0].id)
      } else {
        navigate("/reports/results")
      }
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
    if (windowMode === "sprint") {
      teamRun.mutate({ teamIds: selectedTeamIds })
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
                <option value="sprint">Active sprint</option>
                <option value="date_range">Date range</option>
              </Select>
            </div>
            {windowMode === "sprint" ? (
              <p className="text-xs text-slate-500">
                Runs each team&apos;s active sprint. Kanban teams use their default rolling window.
              </p>
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
        {jobs.length > 0 && (
          <Card>
            <CardContent className="p-4">
              <h2 className="mb-3 text-lg font-semibold">Running / recent</h2>
              <ul className="space-y-2 text-sm" aria-label="report jobs">
                {jobs.map((job) => (
                  <li
                    key={job.id}
                    className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md border px-3 py-2"
                  >
                    <span
                      className={`font-medium ${job.status === "failed" ? "text-red-700" : job.status === "done" ? "text-green-700" : "text-slate-700"}`}
                    >
                      {STATUS_LABEL[job.status]}
                    </span>
                    {job.started_at && (
                      <span className="text-slate-500">
                        Started: {formatTimestamp(job.started_at)}
                      </span>
                    )}
                    {job.finished_at && (
                      <span className="text-slate-500">
                        Finished: {formatTimestamp(job.finished_at)}
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
                ))}
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
