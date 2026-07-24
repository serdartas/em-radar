import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { apiErrorMessage } from "@/lib/api"
import { runTeamReport, type ReportDetail } from "@/lib/reports"
import { listTeams } from "@/lib/teams"

export function ReportRunnerPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const teamsQuery = useQuery({ queryKey: ["teams"], queryFn: listTeams })
  const [selectedTeamIds, setSelectedTeamIds] = useState<string[]>([])

  const openReport = (report: ReportDetail) => {
    void queryClient.invalidateQueries({ queryKey: ["reports"], exact: true })
    navigate(`/reports/results/${report.id}`)
  }

  const teamRun = useMutation({
    mutationFn: async (teamIds: string[]) => {
      let last: ReportDetail | null = null
      for (const teamId of teamIds) {
        last = await runTeamReport(teamId)
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
              {teams.map((team) => (
                <li key={team.id}>
                  <label className="flex items-center gap-3 rounded-md border px-3 py-2 text-sm">
                    <input
                      checked={selectedTeamIds.includes(team.id)}
                      onChange={() => toggleTeam(team.id)}
                      type="checkbox"
                    />
                    <span>{team.name}</span>
                  </label>
                </li>
              ))}
            </ul>
          )}
          <Button
            disabled={running || selectedTeamIds.length === 0}
            onClick={() => teamRun.mutate(selectedTeamIds)}
          >
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
