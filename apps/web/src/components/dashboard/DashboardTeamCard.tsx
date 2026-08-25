// SPDX-License-Identifier: Apache-2.0

import { useMemo } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link } from "react-router-dom"

import { SeverityCounts } from "@/components/SeverityCounts"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { ReportStatusBadge } from "@/components/dashboard/ReportStatusBadge"
import { TopRisksList } from "@/components/dashboard/TopRisksList"
import { apiErrorMessage } from "@/lib/api"
import {
  extractPartialDataNotes,
  type Finding,
  getReport,
  type ReportSummary,
  runTeamReport,
  useFormatTimestamp,
} from "@/lib/reports"
import { teamHasNoSources, type TeamProfile } from "@/lib/teams"

const TOP_RISKS_LIMIT = 3

interface DashboardTeamCardProps {
  team: TeamProfile
  latestSummary: ReportSummary | undefined
  reportsError: boolean
  reportsLoading: boolean
}

function DashboardTeamCard({
  latestSummary,
  reportsError,
  reportsLoading,
  team,
}: DashboardTeamCardProps) {
  const queryClient = useQueryClient()
  const formatTs = useFormatTimestamp()
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
    // A failed run is still persisted as the team's latest report, and the backend re-raises
    // after committing it, so invalidate on settlement rather than success alone. Only the
    // report list needs refetching: details are immutable per report id, and a new latest
    // report brings a new id whose detail query fetches on its own.
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["reports"], exact: true })
    },
  })

  const noSources = teamHasNoSources(team)
  const detail = detailQuery.data
  const topRisksSection = detail?.sections.find((section) => section.section === "top_risks")
  const findingsById = useMemo(
    () => new Map((detail?.findings ?? []).map((finding) => [finding.id, finding])),
    [detail?.findings],
  )
  const topFindings = useMemo(
    () =>
      (topRisksSection?.finding_ids ?? [])
        .slice(0, TOP_RISKS_LIMIT)
        .map((id) => findingsById.get(id))
        .filter((finding): finding is Finding => Boolean(finding)),
    [topRisksSection?.finding_ids, findingsById],
  )
  const partialDataNotes = detail ? extractPartialDataNotes(detail.signal_pack_snapshot) : []

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
            {reportsError && (
              <p
                className="rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800"
                role="alert"
              >
                Report history could not be refreshed. Showing the last loaded report.
              </p>
            )}
            {latestSummary.status === "succeeded" ? (
              <>
                <SeverityCounts counts={latestSummary.findings_count_by_severity} />
                <p className="text-xs text-slate-500">
                  Last run {formatTs(latestSummary.started_at)}
                </p>
                <TopRisksList
                  detail={detail}
                  detailIsError={detailQuery.isError}
                  detailIsLoading={detailQuery.isLoading}
                  topFindings={topFindings}
                />
              </>
            ) : (
              <>
                <ReportStatusBadge
                  error={latestSummary.error}
                  status={latestSummary.status}
                />
                <p className="text-xs text-slate-500">
                  Last run {formatTs(latestSummary.started_at)}
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
          {noSources && <span className="text-xs text-slate-400">no sources attached</span>}
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

export { DashboardTeamCard }
