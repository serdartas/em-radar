import { useMutation } from "@tanstack/react-query"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { type Finding, runDemoReport } from "@/lib/reports"

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

function FindingsPage() {
  const report = useMutation({
    mutationFn: runDemoReport,
  })

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-4xl flex-col px-6 py-12">
      <header className="flex flex-col gap-6 border-b pb-8 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-widest text-slate-500">
            EM Radar
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight">Findings</h1>
          <p className="mt-2 max-w-xl text-slate-600">
            Run the deterministic demo report to inspect engineering management signals.
          </p>
        </div>
        <Button
          disabled={report.isPending}
          onClick={() => report.mutate()}
          size="lg"
        >
          {report.isPending ? "Running demo report..." : "Run demo report"}
        </Button>
      </header>

      <section aria-live="polite" className="mt-8">
        {report.isIdle && (
          <p className="rounded-lg border border-dashed p-8 text-center text-slate-500">
            No report has been run yet.
          </p>
        )}
        {report.isPending && (
          <p className="rounded-lg border p-8 text-center text-slate-500">
            Evaluating demo data...
          </p>
        )}
        {report.isError && (
          <p className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">
            {report.error.message}
          </p>
        )}
        {report.isSuccess && report.data.findings.length === 0 && (
          <p className="rounded-lg border border-dashed p-8 text-center text-slate-500">
            No findings were detected.
          </p>
        )}
        {report.isSuccess && report.data.findings.length > 0 && (
          <>
            <p className="mb-4 text-sm text-slate-500">
              {report.data.findings.length}{" "}
              {report.data.findings.length === 1 ? "finding" : "findings"} detected
            </p>
            <div className="grid gap-4">
              {report.data.findings.map((finding) => (
                <FindingCard
                  finding={finding}
                  key={`${finding.signal_id}-${finding.entity_id}`}
                />
              ))}
            </div>
          </>
        )}
      </section>
    </main>
  )
}

export default FindingsPage
