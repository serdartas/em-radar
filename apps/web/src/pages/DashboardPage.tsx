// SPDX-License-Identifier: Apache-2.0

import { useEffect, useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"

import { DashboardTeamCard } from "@/components/dashboard/DashboardTeamCard"
import { apiErrorMessage } from "@/lib/api"
import { listReports, type ReportSummary } from "@/lib/reports"
import { listTeams } from "@/lib/teams"

/** The most recent report per team, keyed by `team_profile_id`. */
function latestReportByTeam(reports: ReportSummary[]): Map<string, ReportSummary> {
  const latest = new Map<string, ReportSummary>()
  for (const report of reports) {
    if (!report.team_profile_id) {
      continue
    }
    const current = latest.get(report.team_profile_id)
    if (!current || report.started_at > current.started_at) {
      latest.set(report.team_profile_id, report)
    }
  }
  return latest
}

export function DashboardPage() {
  const navigate = useNavigate()
  const teamsQuery = useQuery({ queryKey: ["teams"], queryFn: listTeams })
  const reportsQuery = useQuery({ queryKey: ["reports"], queryFn: listReports })

  // First-run entry: with no team yet, send the user into the onboarding wizard.
  useEffect(() => {
    if (teamsQuery.isSuccess && teamsQuery.data.length === 0) {
      navigate("/setup", { replace: true })
    }
  }, [teamsQuery.isSuccess, teamsQuery.data, navigate])

  const teams = teamsQuery.data ?? []
  const latestByTeam = useMemo(
    () => (reportsQuery.data ? latestReportByTeam(reportsQuery.data) : undefined),
    [reportsQuery.data],
  )

  return (
    <section aria-labelledby="page-title" className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight" id="page-title">
          Dashboard
        </h1>
        <p className="mt-2 max-w-xl text-slate-600">
          The latest report for each team, with its top risks. Refresh to re-run a team&apos;s
          default window.
        </p>
      </header>

      {teamsQuery.isLoading ? (
        <p className="text-sm text-slate-500">Loading teams...</p>
      ) : teamsQuery.isError ? (
        <p className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700" role="alert">
          {apiErrorMessage(teamsQuery.error, "Teams could not be loaded.")}
        </p>
      ) : teams.length === 0 ? (
        <p className="text-sm text-slate-500">No teams yet.</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {teams.map((team) => (
            <DashboardTeamCard
              key={team.id}
              latestSummary={latestByTeam?.get(team.id)}
              reportsError={reportsQuery.isError}
              reportsLoading={reportsQuery.isLoading}
              team={team}
            />
          ))}
        </div>
      )}
    </section>
  )
}
