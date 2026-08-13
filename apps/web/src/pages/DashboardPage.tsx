import { useEffect, useMemo } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate } from "react-router-dom"

import { SeverityCounts } from "@/components/SeverityCounts"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { apiErrorMessage } from "@/lib/api"
import {
  extractPartialDataNotes,
  type Finding,
  formatTimestamp,
  getReport,
  listReports,
  type ReportSummary,
  runTeamReport,
} from "@/lib/reports"
import { listTeams, teamHasNoSources, type TeamProfile } from "@/lib/teams"

const TOP_RISKS_LIMIT = 3

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
            <TeamCard
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

function TeamCard({
  latestSummary,
  reportsError,
  reportsLoading,
  team,
}: {
  latestSummary: ReportSummary | undefined
  reportsError: boolean
  reportsLoading: boolean
  team: TeamProfile
}) {
  const queryClient = useQueryClient()
  const reportId = latestSummary?.id
  const succeeded = latestSummary?.status === "succeeded"
  // Failed runs still persist partial-data notes worth surfacing; running/pending have no
  // meaningful snapshot yet, so skip them.
  const detailAvailable = succeeded || latestSummary?.status === "failed"

  const detailQuery = useQuery({
    queryKey: ["reports", reportId],
    queryFn: () => getReport(reportId as string),
    enabled: Boolean(reportId) && detailAvailable,
  })

  const refresh = useMutation({
    mutationFn: () => runTeamReport(team.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["reports"] })
    },
  })

  const noSources = teamHasNoSources(team)
  const detail = detailQuery.data
  const topRisksSection = detail?.sections.find((section) => section.section === "top_risks")
  const findingsById = new Map((detail?.findings ?? []).map((finding) => [finding.id, finding]))
  const topFindings = (topRisksSection?.finding_ids ?? [])
    .slice(0, TOP_RISKS_LIMIT)
    .map((id) => findingsById.get(id))
    .filter((finding): finding is Finding => Boolean(finding))
  const partialDataNotes = detail
    ? extractPartialDataNotes(detail.signal_pack_snapshot)
    : []

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1">
            <h2 className="text-lg font-semibold leading-snug">{team.name}</h2>
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
              {team.working_mode}
            </p>
          </div>
          {partialDataNotes.length > 0 && (
            <Badge
              className="border-amber-200 bg-amber-50 text-amber-700"
              title="Some sources were unavailable when this report ran. Findings may be incomplete."
            >
              Partial data
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {latestSummary ? (
          <>
            {latestSummary.status === "succeeded" ? (
              <>
                <SeverityCounts counts={latestSummary.findings_count_by_severity} />
                <p className="text-xs text-slate-500">
                  Last run {formatTimestamp(latestSummary.started_at)}
                </p>

                <div className="space-y-2">
                  <h3 className="text-xs font-medium uppercase tracking-wide text-slate-500">
                    Top risks
                  </h3>
                  {detailQuery.isLoading ? (
                    <p className="text-sm text-slate-500">Loading top risks...</p>
                  ) : detailQuery.isError ? (
                    <p className="text-sm text-red-700" role="alert">
                      Top risks could not be loaded.
                    </p>
                  ) : topFindings.length === 0 ? (
                    <p className="text-sm text-slate-500">No risks flagged.</p>
                  ) : (
                    <ul className="space-y-2">
                      {topFindings.map((finding) => (
                        <li
                          className="flex items-start justify-between gap-3"
                          key={finding.id}
                        >
                          <span className="leading-snug">{finding.title}</span>
                          <Badge variant={finding.severity}>{finding.severity}</Badge>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </>
            ) : (
              <>
                <p className="text-xs uppercase tracking-wide text-slate-500">
                  {latestSummary.status}
                </p>
                {latestSummary.status === "failed" ? (
                  <p
                    className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700"
                    role="alert"
                  >
                    Last run failed. {latestSummary.error ?? "The report run failed."}
                  </p>
                ) : (
                  <p className="text-sm text-slate-500">Last run is still in progress.</p>
                )}
                <p className="text-xs text-slate-500">
                  Last run {formatTimestamp(latestSummary.started_at)}
                </p>
              </>
            )}
          </>
        ) : reportsError ? (
          <p
            className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700"
            role="alert"
          >
            Report history could not be loaded.
          </p>
        ) : reportsLoading ? (
          <p className="text-sm text-slate-500">Loading report...</p>
        ) : (
          <p className="text-sm text-slate-500">No report yet.</p>
        )}

        <div className="flex flex-wrap items-center gap-2 border-t pt-4">
          <Button
            disabled={noSources || refresh.isPending}
            onClick={() => refresh.mutate()}
            size="sm"
            title={
              noSources
                ? "Attach a board scope or a code connection to run a report."
                : "Re-run this team's default window."
            }
          >
            {refresh.isPending ? "Refreshing..." : "Refresh"}
          </Button>
          {reportId && (
            <Button asChild size="sm" variant="outline">
              <Link to={`/reports/results/${reportId}`}>Open report</Link>
            </Button>
          )}
          {noSources && (
            <span className="text-xs text-slate-400">no sources attached</span>
          )}
        </div>

        {refresh.isError && (
          <p className="text-sm text-red-700" role="alert">
            {apiErrorMessage(refresh.error, "The report run failed. Please try again.")}
          </p>
        )}
      </CardContent>
    </Card>
  )
}
