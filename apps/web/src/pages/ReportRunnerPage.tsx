import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Select } from "@/components/ui/select"
import { apiErrorMessage } from "@/lib/api"
import { runTeamReport, type ReportDetail } from "@/lib/reports"
import { listTeams, teamHasNoSources } from "@/lib/teams"

type WindowMode = "date_range" | "sprint"

interface TeamRunInput {
  teamIds: string[]
  window?: { start: string; end: string }
}

interface TeamSuccess {
  teamId: string
  teamName: string | null
  report: ReportDetail
}

interface TeamFailure {
  teamId: string
  teamName: string | null
  error: unknown
  message: string
}

interface RunOutcome {
  successes: TeamSuccess[]
  failures: TeamFailure[]
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
  const [allFailures, setAllFailures] = useState<TeamFailure[] | null>(null)

  // Derived before useMutation so the closure captures an initialized binding.
  const teams = teamsQuery.data ?? []

  const teamRun = useMutation({
    mutationFn: async ({ teamIds, window }: TeamRunInput): Promise<RunOutcome> => {
      const successes: TeamSuccess[] = []
      const failures: TeamFailure[] = []
      for (const teamId of teamIds) {
        const teamMeta = teams.find((t) => t.id === teamId)
        const teamName = teamMeta?.name ?? null
        try {
          const report = await runTeamReport(teamId, window)
          successes.push({ teamId, teamName, report })
        } catch (err: unknown) {
          failures.push({
            teamId,
            teamName,
            error: err,
            message: apiErrorMessage(err, "An unexpected error occurred."),
          })
        }
      }
      return { successes, failures }
    },
    onSuccess: ({ successes, failures }: RunOutcome) => {
      if (successes.length >= 1) {
        void queryClient.invalidateQueries({ queryKey: ["reports"], exact: true })
      }
      if (successes.length === 0) {
        setAllFailures(failures)
        return
      }
      if (successes.length === 1 && failures.length === 0) {
        navigate(`/reports/results/${successes[0].report.id}`)
      } else if (failures.length > 0) {
        navigate("/reports/results", {
          state: { failedTeams: failures.map((f) => f.teamName ?? f.teamId) },
        })
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
    setAllFailures(null)
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
        {teamRun.isError && (
          <p className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700" role="alert">
            {apiErrorMessage(teamRun.error, "The report run failed. Please try again.")}
          </p>
        )}
        {allFailures !== null && allFailures.length > 0 && (
          <div
            className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700"
            role="alert"
          >
            <p className="mb-2 font-medium">All team reports failed. No reports were created.</p>
            <ul className="space-y-1 text-sm">
              {allFailures.map((f) => (
                <li key={f.teamId}>
                  {f.teamName ?? f.teamId}: {f.message}
                </li>
              ))}
            </ul>
          </div>
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
