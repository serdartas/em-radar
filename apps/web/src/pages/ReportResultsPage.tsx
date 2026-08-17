// SPDX-License-Identifier: Apache-2.0

import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { Link, useParams } from "react-router-dom"

import { SeverityCounts } from "@/components/SeverityCounts"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import {
  extractPartialDataNotes,
  type Finding,
  formatTimestamp,
  getReport,
  type PartialDataNote,
  type ReportSectionRef,
  reportMarkdownQuery,
  type SkipNote,
} from "@/lib/reports"
import type { Severity } from "@/lib/severity"

export function ReportResultsPage() {
  const { reportId } = useParams<{ reportId: string }>()
  const query = useQuery({
    queryKey: ["reports", reportId],
    queryFn: () => getReport(reportId as string),
    enabled: Boolean(reportId),
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
          <Link className="font-medium text-blue-700 underline-offset-4 hover:underline" to="/reports/results">
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
              Run {formatTimestamp(report.started_at)}
              {report.finished_at && <> · finished {formatTimestamp(report.finished_at)}</>}
            </p>
          </div>
          <ReportExportActions reportId={report.id} />
        </div>
      </header>

      {partialDataNotes.length > 0 && <PartialDataNotes notes={partialDataNotes} />}
      {report.skip_notes.length > 0 && <SkippedSignals notes={report.skip_notes} />}

      {report.status === "failed" ? (
        <p className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700" role="alert">
          {report.error ?? "The report run failed."}
        </p>
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

function ReportSectionBlock({
  findingsById,
  section,
  summaryCounts,
  total,
}: {
  findingsById: Map<string, Finding>
  section: ReportSectionRef
  summaryCounts: Partial<Record<Severity, number>>
  total: number
}) {
  const headingId = `section-${section.section}`
  return (
    <section aria-labelledby={headingId} className="space-y-4">
      <h2 className="text-xl font-semibold tracking-tight" id={headingId}>
        {section.title}
      </h2>
      {section.section === "summary" ? (
        <div className="space-y-2">
          <SeverityCounts counts={summaryCounts} />
          <p className="text-sm text-slate-600">
            {total} finding{total === 1 ? "" : "s"} in total.
          </p>
        </div>
      ) : section.finding_ids.length === 0 ? (
        <p className="text-sm text-slate-500">No findings.</p>
      ) : (
        <div className="grid gap-4">
          {section.finding_ids.map((findingId) => {
            const finding = findingsById.get(findingId)
            return finding ? (
              <FindingCard finding={finding} key={`${section.section}-${findingId}`} />
            ) : null
          })}
        </div>
      )}
    </section>
  )
}

function ReportExportActions({ reportId }: { reportId: string }) {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<"copied" | "error" | "idle">("idle")
  const [busy, setBusy] = useState<"copy" | "download" | null>(null)

  async function handleDownload() {
    setBusy("download")
    setStatus("idle")
    try {
      const markdown = await queryClient.fetchQuery(reportMarkdownQuery(reportId))
      const url = URL.createObjectURL(new Blob([markdown], { type: "text/markdown" }))
      const anchor = document.createElement("a")
      anchor.href = url
      anchor.download = `report-${reportId}.md`
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      // Defer the revoke so the browser can claim the download stream before the
      // blob URL is invalidated (Firefox cancels the download otherwise).
      setTimeout(() => URL.revokeObjectURL(url), 0)
    } catch {
      setStatus("error")
    } finally {
      setBusy(null)
    }
  }

  async function handleCopy() {
    setBusy("copy")
    setStatus("idle")
    try {
      const markdown = await queryClient.fetchQuery(reportMarkdownQuery(reportId))
      await navigator.clipboard.writeText(markdown)
      setStatus("copied")
    } catch {
      setStatus("error")
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="flex flex-col items-start gap-2 sm:items-end">
      <div className="flex flex-wrap gap-2">
        <Button
          disabled={busy !== null}
          onClick={handleDownload}
          size="sm"
          title="Download this report as a Markdown file"
          variant="outline"
        >
          Download .md
        </Button>
        <Button
          disabled={busy !== null}
          onClick={handleCopy}
          size="sm"
          title="Copy the Markdown export to your clipboard"
          variant="outline"
        >
          Copy to clipboard
        </Button>
      </div>
      {status === "copied" && (
        <p aria-live="polite" className="text-xs text-slate-500">
          Copied to clipboard.
        </p>
      )}
      {status === "error" && (
        <p aria-live="polite" className="text-xs text-red-700" role="alert">
          The export could not be generated.
        </p>
      )}
    </div>
  )
}

function PartialDataNotes({ notes }: { notes: PartialDataNote[] }) {
  return (
    <section
      aria-labelledby="partial-data-title"
      className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"
    >
      <h2 className="font-semibold" id="partial-data-title">
        Partial data
      </h2>
      <p className="mt-1 text-amber-800">
        Some sources were unavailable when this report ran. Findings may be incomplete.
      </p>
      <ul className="mt-2 space-y-1">
        {notes.map((note) => (
          <li key={`${note.source}-${note.reason}`}>
            <span className="font-medium">{note.source}</span>: {note.reason}
          </li>
        ))}
      </ul>
    </section>
  )
}

function SkippedSignals({ notes }: { notes: SkipNote[] }) {
  return (
    <section
      aria-labelledby="skipped-signals-title"
      className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700"
    >
      <h2 className="font-semibold" id="skipped-signals-title">
        Skipped signals
      </h2>
      <p className="mt-1 text-slate-600">
        These signals did not run for this report.
      </p>
      <ul className="mt-2 space-y-1">
        {notes.map((note) => (
          <li key={`${note.signal_id}-${note.reason}`}>
            <span className="font-medium">{note.signal_id}</span>: {note.reason}
          </li>
        ))}
      </ul>
    </section>
  )
}

function formatEvidenceValue(value: unknown): string {
  if (value === null) {
    return "null"
  }
  if (typeof value === "string") {
    return value
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value)
  }
  return JSON.stringify(value)
}

function evidenceEntries(evidence: unknown): [string, unknown][] | null {
  if (evidence === null || evidence === undefined) {
    return null
  }
  if (typeof evidence === "object" && !Array.isArray(evidence)) {
    const entries = Object.entries(evidence as Record<string, unknown>)
    return entries.length > 0 ? entries : null
  }
  return null
}

function FindingEvidence({ evidence }: { evidence: unknown }) {
  const entries = evidenceEntries(evidence)
  if (entries) {
    return (
      <div>
        <h4 className="font-semibold">Evidence</h4>
        <ul className="mt-1 space-y-1 text-slate-600">
          {entries.map(([key, value]) => (
            <li key={key}>
              <span className="font-medium">{key}</span>: {formatEvidenceValue(value)}
            </li>
          ))}
        </ul>
      </div>
    )
  }
  if (Array.isArray(evidence)) {
    if (evidence.length === 0) {
      return null
    }
    return (
      <div>
        <h4 className="font-semibold">Evidence</h4>
        <p className="mt-1 text-slate-600">
          {evidence.map((item) => formatEvidenceValue(item)).join(", ")}
        </p>
      </div>
    )
  }
  // Only meaningful scalars remain worth showing. Objects that produced no entries
  // (e.g. `{}`), null, undefined, and empty strings render nothing rather than a bare value.
  const isScalar =
    typeof evidence === "number" ||
    typeof evidence === "boolean" ||
    (typeof evidence === "string" && evidence !== "")
  if (!isScalar) {
    return null
  }
  return (
    <div>
      <h4 className="font-semibold">Evidence</h4>
      <p className="mt-1 text-slate-600">{formatEvidenceValue(evidence)}</p>
    </div>
  )
}

function FindingCard({ finding }: { finding: Finding }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <h3 className="text-lg font-semibold leading-snug">{finding.title}</h3>
          <Badge variant={finding.severity}>{finding.severity}</Badge>
        </div>
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
          {finding.signal_name}
        </p>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div>
          <h4 className="font-semibold">Reason</h4>
          <p className="mt-1 text-slate-600">{finding.reason}</p>
        </div>
        <FindingEvidence evidence={finding.evidence} />
        {finding.recommendation && (
          <div>
            <h4 className="font-semibold">Recommendation</h4>
            <p className="mt-1 text-slate-600">{finding.recommendation}</p>
          </div>
        )}
        {finding.source_link && (
          <a
            className="inline-flex font-medium text-blue-700 underline-offset-4 hover:underline"
            href={finding.source_link}
            rel="noreferrer"
            target="_blank"
          >
            View source
          </a>
        )}
      </CardContent>
    </Card>
  )
}
