// SPDX-License-Identifier: Apache-2.0

import { useQuery } from "@tanstack/react-query"
import { Link, useParams } from "react-router-dom"

import { PartialDataNotes } from "@/components/reports/PartialDataNotes"
import { ReportExportActions } from "@/components/reports/ReportExportActions"
import { ReportSectionBlock } from "@/components/reports/ReportSectionBlock"
import { SignalsChangedBanner } from "@/components/reports/SignalsChangedBanner"
import { SkippedSignals } from "@/components/reports/SkippedSignals"
import {
  extractPartialDataNotes,
  extractSnapshotSignals,
  getReport,
  useFormatTimestamp,
} from "@/lib/reports"
import { listSignalDefinitions } from "@/lib/signalDefinitions"

const REPORT_POLL_MS = 3000

export function ReportResultsPage() {
  const { reportId } = useParams<{ reportId: string }>()
  const formatTs = useFormatTimestamp()
  const query = useQuery({
    queryKey: ["reports", reportId],
    queryFn: () => getReport(reportId as string),
    enabled: Boolean(reportId),
    // Poll while the run is non-terminal so results appear without a manual refresh.
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === "running" || status === "pending" ? REPORT_POLL_MS : false
    },
  })
  const signalsQuery = useQuery({
    queryKey: ["signal-definitions"],
    queryFn: listSignalDefinitions,
  })

  if (query.isLoading) {
    return <p className="text-sm text-slate-500">Loading report…</p>
  }

  if (query.isError || !query.data) {
    return (
      <section aria-labelledby="page-title">
        <h1 className="text-2xl font-semibold tracking-tight" id="page-title">
          Report not found
        </h1>
        <p className="mt-2 text-slate-600">
          This report could not be loaded.{" "}
          <Link
            className="font-medium text-blue-700 underline-offset-4 hover:underline"
            to="/reports/results"
          >
            Back to reports
          </Link>
          .
        </p>
      </section>
    )
  }

  const report = query.data
  const partialDataNotes = extractPartialDataNotes(report.signal_pack_snapshot)
  const findingsById = new Map(report.findings.map((finding) => [finding.id, finding]))
  const snapshotSignals = extractSnapshotSignals(report.signal_pack_snapshot)
  const currentSignals = signalsQuery.data ?? []

  return (
    <section aria-labelledby="page-title" className="space-y-6">
      <header className="space-y-3">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-1">
            <h1 className="text-2xl font-semibold tracking-tight" id="page-title">
              Report Results
            </h1>
            {report.team_name && <p className="text-sm text-slate-600">{report.team_name}</p>}
            <p className="text-xs text-slate-500">
              Run {formatTs(report.started_at)}
              {report.finished_at && <> · finished {formatTs(report.finished_at)}</>}
            </p>
            <p className="text-xs text-slate-400">
              Results reflect signal configuration at run time. Edits to signals affect only future
              runs.
            </p>
          </div>
          <ReportExportActions reportId={report.id} />
        </div>
      </header>

      {snapshotSignals.length > 0 && signalsQuery.data !== undefined && (
        <SignalsChangedBanner currentSignals={currentSignals} snapshotSignals={snapshotSignals} />
      )}

      {partialDataNotes.length > 0 && <PartialDataNotes notes={partialDataNotes} />}
      {report.skip_notes.length > 0 && <SkippedSignals notes={report.skip_notes} />}

      {report.status === "failed" ? (
        <p
          className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700"
          role="alert"
        >
          {report.error ?? "The report run failed."}
        </p>
      ) : report.status === "running" || report.status === "pending" ? (
        <div
          className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600"
          role="status"
        >
          <p className="text-xs uppercase tracking-wide text-slate-500">{report.status}</p>
          <p className="mt-1">
            This report is still running. Results will appear here automatically when it finishes.
          </p>
        </div>
      ) : (
        <div className="space-y-8">
          {report.sections.map((section) => (
            <ReportSectionBlock
              findingsById={findingsById}
              key={section.section}
              section={section}
              summaryCounts={report.summary.counts_by_severity}
              total={report.summary.total}
            />
          ))}
        </div>
      )}
    </section>
  )
}
