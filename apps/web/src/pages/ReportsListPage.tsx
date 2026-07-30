import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"

import { SeverityCounts } from "@/components/SeverityCounts"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { listReports, type ReportSummary } from "@/lib/reports"

function formatTimestamp(value: string): string {
  const parsed = new Date(value)
  return Number.isNaN(parsed.valueOf()) ? value : parsed.toLocaleString()
}

export function ReportsListPage() {
  const query = useQuery({ queryKey: ["reports"], queryFn: listReports })

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
      {query.data && query.data.length > 0 && (
        <ul aria-label="Reports" className="space-y-3">
          {query.data.map((report) => (
            <ReportRow key={report.id} report={report} />
          ))}
        </ul>
      )}
    </section>
  )
}

function ReportRow({ report }: { report: ReportSummary }) {
  return (
    <li>
      <Card>
        <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-1">
            <Link
              className="font-medium text-blue-700 underline-offset-4 hover:underline"
              to={`/reports/results/${report.id}`}
            >
              Report {formatTimestamp(report.started_at)}
            </Link>
            <p className="text-xs uppercase tracking-wide text-slate-500">{report.status}</p>
          </div>
          <SeverityCounts counts={report.findings_count_by_severity} />
        </CardContent>
      </Card>
    </li>
  )
}
