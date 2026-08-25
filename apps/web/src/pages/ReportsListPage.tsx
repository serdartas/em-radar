// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Link, useLocation } from "react-router-dom"

import { SeverityCounts } from "@/components/SeverityCounts"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { listReports, type ReportSummary, useFormatTimestamp } from "@/lib/reports"

interface TeamReportGroup {
  key: string
  teamName: string
  reports: ReportSummary[]
}

// Reports arrive sorted by started_at descending. Grouping by first appearance therefore
// preserves most-recent-first order within each team and orders the groups by their most
// recent report.
function groupReportsByTeam(reports: ReportSummary[]): TeamReportGroup[] {
  const groups = new Map<string, TeamReportGroup>()
  for (const report of reports) {
    const key = report.team_profile_id ?? "unknown"
    const existing = groups.get(key)
    if (existing) {
      existing.reports.push(report)
    } else {
      groups.set(key, {
        key,
        teamName: report.team_name ?? "Unknown team",
        reports: [report],
      })
    }
  }
  return [...groups.values()]
}

export function ReportsListPage() {
  const query = useQuery({ queryKey: ["reports"], queryFn: listReports })
  const groups = query.data ? groupReportsByTeam(query.data) : []
  const location = useLocation()

  // Capture on mount so a subsequent re-render (e.g. after invalidateQueries) does not
  // re-read a stale location.state.
  const [failedTeams] = useState<string[]>(() => {
    const s = location.state
    if (
      s !== null &&
      typeof s === "object" &&
      "failedTeams" in s &&
      Array.isArray((s as Record<string, unknown>).failedTeams)
    ) {
      return ((s as Record<string, unknown>).failedTeams as unknown[]).filter(
        (t): t is string => typeof t === "string",
      )
    }
    return []
  })

  // Clear from browser history after mount so a manual refresh does not replay the note.
  // Guard on failedTeams so we never clobber React Router's internal history fields
  // (usr/key/idx) on pages that had no payload to consume.
  useEffect(() => {
    if (failedTeams.length > 0) {
      window.history.replaceState({ ...window.history.state, usr: null }, "")
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <section aria-labelledby="page-title" className="space-y-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight" id="page-title">
            Report Results
          </h1>
          <p className="mt-2 max-w-xl text-slate-600">
            Every report run is stored locally. Open one to review its findings.
          </p>
        </div>
        <Button asChild>
          <Link to="/reports/run">Run a report</Link>
        </Button>
      </header>

      {failedTeams.length > 0 && (
        <p
          className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-amber-700"
          role="alert"
        >
          {`Report generation failed for ${failedTeams.join(", ")}. Successful reports were still created.`}
        </p>
      )}
      {query.isLoading && <p className="text-sm text-slate-500">Loading reports…</p>}
      {query.isError && (
        <p className="text-sm text-red-700" role="alert">
          Reports could not be loaded.
        </p>
      )}
      {query.data && query.data.length === 0 && (
        <p className="rounded-lg border border-dashed p-8 text-center text-sm text-slate-500">
          No reports yet. Run a report to create one.
        </p>
      )}
      {groups.length > 0 && (
        <div className="space-y-8">
          {groups.map((group) => (
            <TeamReportGroupSection group={group} key={group.key} />
          ))}
        </div>
      )}
    </section>
  )
}

function TeamReportGroupSection({ group }: { group: TeamReportGroup }) {
  const headingId = `team-${group.key}`
  return (
    <section aria-labelledby={headingId} className="space-y-3">
      <h2 className="text-lg font-semibold tracking-tight" id={headingId}>
        {group.teamName}
      </h2>
      <ul aria-labelledby={headingId} className="space-y-3">
        {group.reports.map((report) => (
          <ReportRow key={report.id} report={report} />
        ))}
      </ul>
    </section>
  )
}

function ReportRow({ report }: { report: ReportSummary }) {
  const formatTs = useFormatTimestamp()
  return (
    <li>
      <Card>
        <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-1">
            <Link
              className="font-medium text-blue-700 underline-offset-4 hover:underline"
              to={`/reports/results/${report.id}`}
            >
              Report {formatTs(report.started_at)}
            </Link>
            <p className="text-xs uppercase tracking-wide text-slate-500">{report.status}</p>
          </div>
          <SeverityCounts counts={report.findings_count_by_severity} />
        </CardContent>
      </Card>
    </li>
  )
}
