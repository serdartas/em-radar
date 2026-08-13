import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Select } from "@/components/ui/select"
import { apiErrorMessage } from "@/lib/api"
import { runTeamReport, type ReportDetail } from "@/lib/reports"
import { listTeams, type TeamProfile } from "@/lib/teams"

type WindowMode = "date_range" | "sprint"

interface TeamRunInput {
  teamIds: string[]
  window?: { start: string; end: string }
}

/** A team with no board scope and no code connection has no sources and cannot run a report. */
function teamHasNoSources(team: TeamProfile): boolean {
  return team.scope_ids.length === 0 && !team.code_connection_id
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

  const openReport = (report: ReportDetail) => {
    void queryClient.invalidateQueries({ queryKey: ["reports"], exact: true })
    navigate(`/reports/results/${report.id}`)
  }

  const teamRun = useMutation({
    mutationFn: async ({ teamIds, window }: TeamRunInput) => {
      let last: ReportDetail | null = null
      for (const teamId of teamIds) {
        last = await runTeamReport(teamId, window)
      }
      return last
    },
    onSuccess: (report) => {
      if (report) {
        openReport(report)
      }
    },
  })

  const teams = teamsQuery.data ?? []
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
    const end = `${endDate}T00:00:00Z`
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
                <option value="sprint">Sprint</option>
                <option value="date_range">Date range</option>
              </Select>
            </div>
            {windowMode === "sprint" ? (
              <p className="text-xs text-slate-500">
                Uses each team&apos;s current sprint or default window.
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
