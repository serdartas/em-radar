import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { Link, useParams } from "react-router-dom"

import { SeverityCounts } from "@/components/SeverityCounts"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { type Finding, getReport, getReportMarkdown } from "@/lib/reports"

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

  return (
    <section aria-labelledby="page-title" className="space-y-6">
      <header className="space-y-3">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <h1 className="text-2xl font-semibold tracking-tight" id="page-title">
            Report Results
          </h1>
          <ReportExportActions reportId={report.id} />
        </div>
        <SeverityCounts counts={report.findings_count_by_severity} />
      </header>

      {report.status === "failed" ? (
        <p className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700" role="alert">
          {report.error ?? "The report run failed."}
        </p>
      ) : report.findings.length === 0 ? (
        <p className="rounded-lg border border-dashed p-8 text-center text-sm text-slate-500">
          No findings were detected.
        </p>
      ) : (
        <div className="grid gap-4">
          {report.findings.map((finding) => (
            <FindingCard finding={finding} key={`${finding.signal_id}-${finding.entity_id}`} />
          ))}
        </div>
      )}
    </section>
  )
}

function ReportExportActions({ reportId }: { reportId: string }) {
  const [status, setStatus] = useState<"copied" | "error" | "idle">("idle")
  const [busy, setBusy] = useState<"copy" | "download" | null>(null)

  async function handleDownload() {
    setBusy("download")
    setStatus("idle")
    try {
      const markdown = await getReportMarkdown(reportId)
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
      const markdown = await getReportMarkdown(reportId)
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

function FindingCard({ finding }: { finding: Finding }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <h2 className="text-lg font-semibold leading-snug">{finding.title}</h2>
          <Badge variant={finding.severity}>{finding.severity}</Badge>
        </div>
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
          {finding.signal_name}
        </p>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div>
          <h3 className="font-semibold">Reason</h3>
          <p className="mt-1 text-slate-600">{finding.reason}</p>
        </div>
        {finding.recommendation && (
          <div>
            <h3 className="font-semibold">Recommendation</h3>
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
